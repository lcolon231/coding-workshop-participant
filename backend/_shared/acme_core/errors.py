"""The error envelope shared by every ACME service.

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


class AppError(Exception):
    """Base class for every expected failure.

    Subclasses declare `code` and `status`; `__init_subclass__` enforces it, so
    an error without a status fails at import rather than at the first 500.
    """

    code: ClassVar[str]
    status: ClassVar[int]
    default_message: ClassVar[str] = "Request failed."

    def __init_subclass__(cls, **kwargs: Any) -> None:
        """Reject a subclass that omits its code or status."""
        super().__init_subclass__(**kwargs)
        for required in ("code", "status"):
            if not getattr(cls, required, None):
                raise TypeError(f"{cls.__name__} must define a class-level {required!r}")

    def __init__(
        self,
        message: str | None = None,
        *,
        details: list[dict[str, str]] | None = None,
    ) -> None:
        """Create the error.

        Args:
            message: Human-readable text; defaults to the class default.
            details: Field-level problems, each `{"field": ..., "message": ...}`.
        """
        self.message = message or self.default_message
        self.details = details or []
        super().__init__(self.message)


class ValidationFailed(AppError):
    """Request body, query or path failed validation."""

    code = "validation_error"
    status = 400
    default_message = "Request validation failed."


class Unauthenticated(AppError):
    """No usable credentials were presented."""

    code = "unauthenticated"
    status = 401
    default_message = "Authentication required."


class TokenExpired(AppError):
    """The presented token is well-formed but past its expiry."""

    code = "token_expired"
    status = 401
    default_message = "Token has expired."


class WrongTokenType(AppError):
    """A refresh token was presented where an access token is required."""

    code = "wrong_token_type"
    status = 401
    default_message = "Token is not valid for this endpoint."


class Forbidden(AppError):
    """Authenticated, but the role or relationship does not permit this."""

    code = "forbidden"
    status = 403
    default_message = "You do not have permission to perform this action."


class NotFound(AppError):
    """No such resource, or it is outside the caller's visibility.

    Deliberately the same answer for both. Returning 403 for an out-of-scope
    row would confirm that the row exists.
    """

    code = "not_found"
    status = 404
    default_message = "Resource not found."


class Conflict(AppError):
    """The request collides with existing state."""

    code = "conflict"
    status = 409
    default_message = "Request conflicts with the current state."


class RefreshTokenReused(AppError):
    """A rotated refresh token was presented again.

    Treated as theft: the whole token family is revoked.
    """

    code = "refresh_token_reused"
    status = 409
    default_message = "Refresh token has already been used; the session was revoked."


class InvalidTransition(AppError):
    """The requested status change is not a legal edge of the workflow."""

    code = "invalid_transition"
    status = 409
    default_message = "That status change is not allowed."


class InternalError(AppError):
    """Catch-all for an unexpected failure."""

    code = "internal_error"
    status = 500
    default_message = "An internal error occurred."


def all_error_classes() -> list[type[AppError]]:
    """Return every concrete AppError subclass, depth-first.

    Returns:
        The subclasses, which the test suite uses to assert the catalog is
        complete and that no two share a code.
    """
    found: list[type[AppError]] = []
    stack = list(AppError.__subclasses__())
    while stack:
        cls = stack.pop()
        # __init_subclass__ runs *after* Python registers the class, so a
        # definition it rejects still appears here until it is collected.
        # Such a class is not a usable error, so skip it.
        if getattr(cls, "code", None) and getattr(cls, "status", None):
            found.append(cls)
        stack.extend(cls.__subclasses__())
    return found


def error_catalog() -> dict[str, int]:
    """Map every error code to its HTTP status.

    Returns:
        A `code -> status` mapping derived from the class hierarchy, so it
        cannot drift from the errors that actually exist.
    """
    return {cls.code: cls.status for cls in all_error_classes()}


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
