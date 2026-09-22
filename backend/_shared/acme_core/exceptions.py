"""The application error hierarchy.

Deliberately free of any web-framework import. `workflow.py` and the domain
services raise these, and the admin invocation path -- migrate and seed --
imports them too. If this module pulled in FastAPI, a `{"action": "migrate"}`
invoke would pay the entire web stack's import cost on a 128 MB Lambda, which
is exactly what the lazy adapter in function.py exists to prevent.

The FastAPI handlers that render these live in `acme_core.errors`.
"""

from __future__ import annotations

from typing import Any, ClassVar


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

    Treated as theft: the whole token family is revoked. A 401 rather than a
    409 because the client's only correct response is to sign in again, and
    its refresh interceptor already does exactly that on any 401 from /refresh.
    """

    code = "refresh_token_reused"
    status = 401
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
