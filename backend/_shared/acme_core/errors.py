"""Rendering the error envelope for HTTP.

The exception hierarchy itself lives in `acme_core.exceptions`, which imports
no web framework. This module adds the FastAPI handlers that turn those into
responses, and re-exports the hierarchy so callers need only one import.

One shape for every failure, in every service, so a client needs exactly one
branch to handle errors:

    {"error": "validation_error",
     "message": "Request validation failed.",
     "details": [{"field": "email", "message": "..."}],
     "request_id": "8f2e-a11c"}

`error` is a stable machine code rather than prose. `token_expired` and
`refresh_token_reused` are both 401 but call for opposite client behaviour --
silently refresh versus force a re-login -- and a status code alone cannot say
which.
"""

from __future__ import annotations

from typing import Any, ClassVar

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException as StarletteHTTPException

from acme_core.exceptions import (
    AppError,
    Conflict,
    Forbidden,
    InternalError,
    InvalidTransition,
    NotFound,
    RefreshTokenReused,
    TokenExpired,
    Unauthenticated,
    ValidationFailed,
    WrongTokenType,
    all_error_classes,
    error_catalog,
)
from acme_core.logging_config import get_logger, get_request_id

_logger = get_logger(__name__)

# Location prefixes Pydantic reports that name the request part, not a field.
_LOCATION_PREFIXES = frozenset({"body", "query", "path", "header", "cookie"})


class ErrorDetail(BaseModel):
    """One field-level validation problem."""

    field: str = Field(description="Dotted path to the offending field.", examples=["email"])
    message: str = Field(
        description="What was wrong with it.",
        examples=["must be an @acme.inc address"],
    )


class ErrorResponse(BaseModel):
    """The envelope returned by every failure, in every service.

    `error` is a stable machine-readable code, not prose: `token_expired` and
    `refresh_token_reused` are both 401 but call for opposite client behaviour,
    and a status code alone cannot distinguish them.
    """

    error: str = Field(
        description="Stable machine-readable code. Switch on this, not on the message.",
        examples=["validation_error"],
    )
    message: str = Field(
        description="Human-readable summary, safe to show a user.",
        examples=["Request validation failed."],
    )
    details: list[ErrorDetail] = Field(
        default_factory=list,
        description="Field-level problems. Always present; empty when not applicable.",
    )
    request_id: str | None = Field(
        default=None,
        description="Correlation id, also returned in the X-Request-Id header.",
    )


# Reusable OpenAPI response blocks, so every service documents failures the
# same way instead of each route inventing its own.
def error_responses(*statuses: int) -> dict[int | str, dict[str, object]]:
    """Build OpenAPI `responses` entries for the given status codes.

    Args:
        statuses: HTTP status codes this endpoint can fail with.

    Returns:
        A mapping suitable for a FastAPI route's `responses` argument.
    """
    described = {
        400: "Validation failed. `details` names the offending fields.",
        401: "Missing, expired or wrong-type token.",
        403: "Authenticated, but not permitted.",
        404: "Not found, or outside your visibility.",
        409: "Conflicts with current state.",
        500: "Unexpected error. The message is scrubbed; quote `request_id`.",
    }
    return {
        status: {"model": ErrorResponse, "description": described.get(status, "Error.")}
        for status in statuses
    }


def build_envelope(
    code: str,
    message: str,
    details: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """Build the response body.

    Args:
        code: Stable machine-readable error code.
        message: Human-readable summary.
        details: Field-level problems.

    Returns:
        The envelope, always with the same four keys.
    """
    return {
        "error": code,
        "message": message,
        "details": details or [],
        "request_id": get_request_id(),
    }


def details_from_validation(exc: RequestValidationError) -> list[dict[str, str]]:
    """Convert a Pydantic validation error into field-level details.

    Only `loc` and `msg` are read. Pydantic's error dicts also carry `input`,
    which holds the *submitted value* -- copying that wholesale would echo a
    rejected password back in the response body and into the logs. Building the
    output explicitly means a future Pydantic key cannot leak by default.

    Args:
        exc: The validation error raised by FastAPI.

    Returns:
        One `{"field", "message"}` entry per problem.
    """
    details: list[dict[str, str]] = []
    for err in exc.errors():
        parts = [str(p) for p in err.get("loc", ()) if p not in _LOCATION_PREFIXES]
        details.append(
            {
                "field": ".".join(parts) or "__root__",
                "message": str(err.get("msg", "Invalid value.")),
            }
        )
    return details


def _json(status: int, body: dict[str, Any]) -> JSONResponse:
    """Serialise an envelope, adding the auth challenge header on a 401.

    Args:
        status: HTTP status code.
        body: The envelope.

    Returns:
        The response.
    """
    headers = {"WWW-Authenticate": "Bearer"} if status == 401 else None
    return JSONResponse(status_code=status, content=body, headers=headers)


async def handle_app_error(_request: Request, exc: Exception) -> JSONResponse:
    """Render a known AppError."""
    err = exc if isinstance(exc, AppError) else InternalError()
    return _json(err.status, build_envelope(err.code, err.message, err.details))


async def handle_validation_error(_request: Request, exc: Exception) -> JSONResponse:
    """Render a request validation failure as 400, not FastAPI's default 422."""
    details = details_from_validation(exc) if isinstance(exc, RequestValidationError) else []
    return _json(
        ValidationFailed.status,
        build_envelope(ValidationFailed.code, ValidationFailed.default_message, details),
    )


async def handle_http_exception(_request: Request, exc: Exception) -> JSONResponse:
    """Render Starlette's own HTTPException in the shared envelope.

    Routing failures (404, 405) are raised by the framework, not by us, and
    would otherwise return a differently-shaped body.
    """
    status = exc.status_code if isinstance(exc, StarletteHTTPException) else 500
    detail = getattr(exc, "detail", None)
    by_status = {cls.status: cls for cls in all_error_classes()}
    cls = by_status.get(status, InternalError)
    return _json(status, build_envelope(cls.code, str(detail or cls.default_message)))


async def handle_unexpected_error(_request: Request, exc: Exception) -> JSONResponse:
    """Render an unhandled exception without leaking its message.

    The message is scrubbed but `request_id` is kept, so the detail is one
    CloudWatch query away while the client learns nothing about internals.
    """
    _logger.exception("unhandled_exception", extra={"request_id": get_request_id()})
    return _json(
        InternalError.status,
        build_envelope(InternalError.code, InternalError.default_message),
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Install every handler on an application.

    Args:
        app: The FastAPI application to configure.
    """
    app.add_exception_handler(AppError, handle_app_error)
    app.add_exception_handler(RequestValidationError, handle_validation_error)
    app.add_exception_handler(StarletteHTTPException, handle_http_exception)
    app.add_exception_handler(Exception, handle_unexpected_error)


__all__ = [
    "AppError",
    "Conflict",
    "ErrorDetail",
    "ErrorResponse",
    "Forbidden",
    "InternalError",
    "InvalidTransition",
    "NotFound",
    "RefreshTokenReused",
    "TokenExpired",
    "Unauthenticated",
    "ValidationFailed",
    "WrongTokenType",
    "all_error_classes",
    "build_envelope",
    "details_from_validation",
    "error_catalog",
    "error_responses",
    "register_exception_handlers",
]
