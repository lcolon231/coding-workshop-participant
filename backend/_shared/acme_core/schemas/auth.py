"""Request and response bodies for authentication."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Annotated

from pydantic import EmailStr, Field, field_validator

from acme_core.config import get_settings
from acme_core.models.enums import Role
from acme_core.schemas.common import ResponseModel, StrictModel
from acme_core.security.passwords import MAX_PASSWORD_BYTES, MIN_PASSWORD_LENGTH

Password = Annotated[str, Field(min_length=MIN_PASSWORD_LENGTH, max_length=MAX_PASSWORD_BYTES)]


class _EmailNormalising(StrictModel):
    """Mixin that lower-cases an email before anything else sees it."""

    @field_validator("email", mode="before", check_fields=False)
    @classmethod
    def _normalise(cls, value: object) -> object:
        """Lower-case and trim, so the unique index is case-insensitive."""
        return value.strip().lower() if isinstance(value, str) else value


class RegisterRequest(_EmailNormalising):
    """Self-registration.

    Note what is absent: there is no `role`. Self-registration always creates
    an Employee, and the field cannot be supplied at all -- `extra="forbid"`
    turns an attempt into a 400 rather than a silently ignored escalation.
    """

    email: EmailStr
    password: Password
    full_name: Annotated[str, Field(min_length=1, max_length=200)]

    @field_validator("email")
    @classmethod
    def _company_domain(cls, value: str) -> str:
        """Restrict self-registration to the company domain.

        This is input validation, not authentication: nothing here proves the
        registrant controls the address. Treating it as an authentication
        boundary would be a mistake, and it is documented as such.
        """
        domain = get_settings().signup_domain
        # Compare the domain exactly, so `user@acme.inc.evil.com` is rejected.
        if value.rsplit("@", 1)[-1] != domain:
            raise ValueError(f"must be an @{domain} address")
        return value


class LoginRequest(_EmailNormalising):
    """Credentials."""

    email: EmailStr
    password: Annotated[str, Field(min_length=1, max_length=MAX_PASSWORD_BYTES)]


class RefreshRequest(StrictModel):
    """Exchange a refresh token for a new pair."""

    refresh_token: Annotated[str, Field(min_length=1)]


class TokenPair(ResponseModel):
    """Newly issued tokens."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = Field(description="Access token lifetime in seconds.")


class UserOut(ResponseModel):
    """A user, as returned to a client.

    Carries no password hash, and no lockout counters: those are operational
    state, not something a client needs or should be able to probe.
    """

    id: uuid.UUID
    email: str
    full_name: str
    role: Role
    is_active: bool
    created_at: dt.datetime


class AdminCreateUserRequest(_EmailNormalising):
    """Admin-only user creation.

    The one place a role may be chosen, which is why it exists separately from
    RegisterRequest rather than as an optional field on it.
    """

    email: EmailStr
    password: Password
    full_name: Annotated[str, Field(min_length=1, max_length=200)]
    role: Role
    specialty: Annotated[str | None, Field(max_length=100)] = None


class AdminUpdateUserRequest(StrictModel):
    """Admin-only user update. Every field optional; omitted means unchanged."""

    full_name: Annotated[str | None, Field(min_length=1, max_length=200)] = None
    role: Role | None = None
    is_active: bool | None = None
