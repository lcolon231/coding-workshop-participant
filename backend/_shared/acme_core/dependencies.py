"""FastAPI dependencies shared by every service.

Authentication lives here, not in the auth service, because all three services
authenticate the same way: verify the access token, then load the user row and
take role and activity from it. A per-service copy is how one of them ends up
trusting the token's claims.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from acme_core.db.engine import get_db
from acme_core.exceptions import Unauthenticated
from acme_core.models.user import User
from acme_core.security.principal import (
    Principal,
    ensure_active,
    ensure_session_not_revoked,
    require_admin,
)
from acme_core.security.secret import get_jwt_secret
from acme_core.security.tokens import TokenType, decode_token

# auto_error=False: FastAPI's own failure is a bare 403 (or 401, by version)
# outside our envelope. We raise Unauthenticated ourselves, which carries the
# envelope and the WWW-Authenticate challenge.
_bearer = HTTPBearer(
    auto_error=False,
    description=(
        "An access token from POST /api/auth/login. Behind CloudFront send it as "
        "`X-Acme-Authorization: Bearer <token>` instead: the distribution signs each "
        "origin request with its own Authorization header and drops the viewer's."
    ),
)

# The header the browser client uses. On AWS the API sits behind CloudFront,
# whose origin access control signs every request to the Lambda function URLs
# with SigV4 and overwrites the viewer's `Authorization` header in doing so
# (the only alternative, `no-override`, would require the browser to produce
# SigV4 signatures itself). A header of our own passes through untouched.
# `Authorization` is still honoured, for curl, the Swagger page and tests.
ALT_AUTHORIZATION_HEADER = "x-acme-authorization"
_BEARER_SCHEME = "bearer"

# scope="function": commit and close before the response is sent, so a client that
# reads right after a 2xx sees the write, and a failed commit cannot follow a 2xx.
# FastAPI 0.118+ defaults yield dependencies to "request" scope, which runs the
# exit code after the response.
DbSession = Annotated[Session, Depends(get_db, scope="function")]


def _alternate_bearer(request: Request) -> str | None:
    """Return the token from `X-Acme-Authorization`, or None when absent.

    Raises:
        Unauthenticated: The header is present but is not `Bearer <token>`.
    """
    raw = request.headers.get(ALT_AUTHORIZATION_HEADER)
    if raw is None:
        return None
    scheme, _, token = raw.strip().partition(" ")
    token = token.strip()
    if scheme.lower() != _BEARER_SCHEME or not token:
        raise Unauthenticated("Authentication required.")
    return token


def bearer_token(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> str:
    """Extract the bearer token, or refuse the request.

    `X-Acme-Authorization` is read first: behind CloudFront the standard
    header carries the edge's own SigV4 signature, never the viewer's token.

    Args:
        request: The request, for the alternate header.
        credentials: The parsed Authorization header, if any.

    Returns:
        The raw token.

    Raises:
        Unauthenticated: No bearer token was sent in either header.
    """
    alternate = _alternate_bearer(request)
    if alternate is not None:
        return alternate
    if credentials is None or not credentials.credentials:
        raise Unauthenticated("Authentication required.")
    return credentials.credentials


def current_user(
    token: Annotated[str, Depends(bearer_token)],
    session: DbSession,
) -> User:
    """Authenticate the request and return the caller's user row.

    The token proves identity only. Role and `is_active` are read from the row
    fetched here, so a demotion or deactivation takes effect on the very next
    request rather than when the access token happens to expire (S7).

    Args:
        token: The bearer token.
        session: The request's database session.

    Returns:
        The authenticated, active user.

    Raises:
        TokenExpired: The access token has expired.
        WrongTokenType: A refresh token was presented.
        Unauthenticated: The token is invalid, the user is gone or inactive,
            or the session was revoked after the token was issued.
    """
    claims = decode_token(token, get_jwt_secret(session), expected_type=TokenType.ACCESS)
    user = session.get(User, claims.subject)
    if user is None:
        # Same message as a deactivated account: a deleted user and a
        # disabled one should be indistinguishable to whoever holds the token.
        raise Unauthenticated("Authentication required.")
    ensure_active(user)
    ensure_session_not_revoked(user, claims.issued_at)
    return user


CurrentUser = Annotated[User, Depends(current_user)]


def current_principal(user: CurrentUser) -> Principal:
    """Return the caller as a Principal, for authorisation decisions.

    Args:
        user: The authenticated user.

    Returns:
        The principal built from the database row.
    """
    return Principal.from_user(user)


CurrentPrincipal = Annotated[Principal, Depends(current_principal)]


def admin_principal(principal: CurrentPrincipal) -> Principal:
    """Admit only Facility Admins.

    Runs before any row lookup, so a 403 here never reveals whether the
    resource the caller asked for exists.

    Args:
        principal: The authenticated caller.

    Returns:
        The same principal.

    Raises:
        Forbidden: The caller is not an admin.
    """
    return require_admin(principal)


AdminPrincipal = Annotated[Principal, Depends(admin_principal)]
