"""Issuing and verifying JSON Web Tokens."""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Final

import jwt

from acme_core.config import get_settings
from acme_core.exceptions import TokenExpired, Unauthenticated, WrongTokenType

# Hardcoded, never read from the token's own header. Deriving the algorithm
# from untrusted input is the classic JWT break: an attacker sets alg to "none"
# or swaps HS256 for RS256 and supplies their own key.
ALGORITHM: Final[str] = "HS256"
ISSUER_PREFIX: Final[str] = "acme-auth"
# Tolerance for clock drift between whatever issued a token and whatever checks
# it. Small enough to be meaningless to an attacker, large enough that a Lambda
# a few seconds out of step does not log everyone out.
CLOCK_SKEW_LEEWAY_SECONDS: Final[int] = 30
AUDIENCE: Final[str] = "acme-api"


class TokenType(StrEnum):
    """Which endpoints a token is valid at.

    Carried in the `typ` claim. Without it a stolen 7-day refresh token would
    authenticate ordinary API calls for a week.
    """

    ACCESS = "access"
    REFRESH = "refresh"


@dataclass(frozen=True, slots=True)
class TokenClaims:
    """The verified contents of a token."""

    subject: uuid.UUID
    token_type: TokenType
    jti: uuid.UUID
    issued_at: dt.datetime
    expires_at: dt.datetime

    @property
    def issued_at_epoch(self) -> int:
        """Return `iat` as an integer, for comparison against a session cutoff."""
        return int(self.issued_at.timestamp())


def _issuer() -> str:
    """Return the issuer for this deployment."""
    return f"{ISSUER_PREFIX}-{get_settings().service_name}"


def issue_token(
    subject: uuid.UUID,
    token_type: TokenType,
    secret: str,
    *,
    now: dt.datetime | None = None,
    lifetime_seconds: int | None = None,
) -> tuple[str, TokenClaims]:
    """Mint a signed token.

    Args:
        subject: The user the token identifies.
        token_type: Access or refresh.
        secret: The signing key.
        now: Issue time; defaults to the current UTC time.
        lifetime_seconds: Override the configured lifetime.

    Returns:
        The encoded token and its claims. The claims are returned so a caller
        can persist `jti` and `expires_at` without decoding what it just made.
    """
    settings = get_settings()
    issued = now or dt.datetime.now(dt.UTC)
    if lifetime_seconds is None:
        lifetime_seconds = (
            settings.access_ttl_seconds
            if token_type is TokenType.ACCESS
            else settings.refresh_ttl_seconds
        )
    expires = issued + dt.timedelta(seconds=lifetime_seconds)
    jti = uuid.uuid4()

    payload: dict[str, Any] = {
        "sub": str(subject),
        "typ": token_type.value,
        "jti": str(jti),
        "iat": int(issued.timestamp()),
        "exp": int(expires.timestamp()),
        "iss": _issuer(),
        "aud": AUDIENCE,
    }
    encoded = jwt.encode(payload, secret, algorithm=ALGORITHM)
    return encoded, TokenClaims(
        subject=subject, token_type=token_type, jti=jti,
        issued_at=issued, expires_at=expires,
    )


def decode_token(
    token: str,
    secret: str,
    *,
    expected_type: TokenType | None = None,
) -> TokenClaims:
    """Verify a token and return its claims.

    Args:
        token: The encoded token.
        secret: The signing key.
        expected_type: Reject the token unless its `typ` matches.

    Returns:
        The verified claims.

    Raises:
        TokenExpired: Past its expiry.
        WrongTokenType: Valid, but not usable at this endpoint.
        Unauthenticated: Malformed, mis-signed, or missing a required claim.
    """
    try:
        payload = jwt.decode(
            token,
            secret,
            algorithms=[ALGORITHM],
            leeway=CLOCK_SKEW_LEEWAY_SECONDS,
            audience=AUDIENCE,
            issuer=_issuer(),
            options={"require": ["sub", "typ", "jti", "iat", "exp", "iss", "aud"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise TokenExpired() from exc
    except jwt.InvalidTokenError as exc:
        # Covers a bad signature, alg:none, a wrong audience or issuer, and a
        # missing required claim. All are "we do not know who you are".
        raise Unauthenticated("Token is not valid.") from exc

    raw_type = payload.get("typ")
    try:
        token_type = TokenType(raw_type)
    except ValueError as exc:
        # Fail closed: an unrecognised typ is rejected, never defaulted.
        raise Unauthenticated("Token is not valid.") from exc

    if expected_type is not None and token_type is not expected_type:
        raise WrongTokenType(
            f"This endpoint requires a {expected_type.value} token."
        )

    try:
        subject = uuid.UUID(payload["sub"])
        jti = uuid.UUID(payload["jti"])
    except (ValueError, TypeError, KeyError) as exc:
        raise Unauthenticated("Token is not valid.") from exc

    return TokenClaims(
        subject=subject,
        token_type=token_type,
        jti=jti,
        issued_at=dt.datetime.fromtimestamp(payload["iat"], tz=dt.UTC),
        expires_at=dt.datetime.fromtimestamp(payload["exp"], tz=dt.UTC),
    )


def hash_refresh_token(token: str) -> str:
    """Hash a refresh token for storage.

    Uses SHA-256 rather than bcrypt: the input is already 256 bits of signed
    random data, so there is nothing to slow an attacker down about, and lookup
    happens on every refresh. A database disclosure still yields no usable
    credential.

    Args:
        token: The encoded refresh token.

    Returns:
        A hex digest suitable for an indexed unique column.
    """
    import hashlib

    return hashlib.sha256(token.encode("utf-8")).hexdigest()
