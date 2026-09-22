"""Request and response bodies for authentication and user administration."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Annotated, ClassVar

from pydantic import EmailStr, Field, field_validator, model_validator

from acme_core.config import get_settings
from acme_core.models.enums import Role
from acme_core.schemas.common import (
    Order,
    PageParams,
    ResponseModel,
    StrictModel,
    UpdateModel,
)
from acme_core.security.passwords import MAX_PASSWORD_BYTES, MIN_PASSWORD_LENGTH

Password = Annotated[str, Field(min_length=MIN_PASSWORD_LENGTH, max_length=MAX_PASSWORD_BYTES)]
FullName = Annotated[str, Field(min_length=1, max_length=200)]
Specialty = Annotated[str, Field(min_length=1, max_length=100)]


def _require_company_domain(value: str) -> str:
    """Restrict an address to the company domain.

    This is input validation, not authentication: nothing here proves the
    address belongs to whoever typed it. Treating it as an authentication
    boundary would be a mistake, and it is documented as such.

    Args:
        value: An already lower-cased, trimmed email address.

    Returns:
        The address, unchanged.

    Raises:
        ValueError: The domain is not exactly the signup domain.
    """
    domain = get_settings().signup_domain
    # Compare the domain exactly, so `user@acme.inc.evil.com` is rejected.
    if value.rsplit("@", 1)[-1] != domain:
        raise ValueError(f"must be an @{domain} address")
    return value


class _EmailNormalising(StrictModel):
    """Mixin that lower-cases an email before anything else sees it."""

    @field_validator("email", mode="before", check_fields=False)
    @classmethod
    def _normalise(cls, value: object) -> object:
        """Lower-case and trim, so the unique index is case-insensitive."""
        return value.strip().lower() if isinstance(value, str) else value


class _CompanyEmail(_EmailNormalising):
    """Mixin restricting `email` to the company domain, after normalising."""

    @field_validator("email", check_fields=False)
    @classmethod
    def _company_domain(cls, value: str) -> str:
        """Apply the shared domain rule."""
        return _require_company_domain(value)


class RegisterRequest(_CompanyEmail):
    """Self-registration.

    Note what is absent: there is no `role`. Self-registration always creates
    an Employee, and the field cannot be supplied at all -- `extra="forbid"`
    turns an attempt into a 400 rather than a silently ignored escalation.
    """

    email: EmailStr
    password: Password
    full_name: FullName


class RegisterAccepted(ResponseModel):
    """The register response, identical whether or not the email was new.

    A 202 carrying only a message: returning the created user would confirm
    that an existing address was *not* re-created, which is the enumeration
    the endpoint is designed not to answer.
    """

    message: str


class LoginRequest(_EmailNormalising):
    """Credentials."""

    email: EmailStr
    password: Annotated[str, Field(min_length=1, max_length=MAX_PASSWORD_BYTES)]


class RefreshRequest(StrictModel):
    """Exchange a refresh token for a new pair, or revoke it on logout."""

    refresh_token: Annotated[str, Field(min_length=1)]


class ChangePasswordRequest(StrictModel):
    """Change one's own password.

    The current password is required even though the caller is authenticated:
    an access token left on an unlocked screen must not be enough to take the
    account over permanently.
    """

    current_password: Annotated[str, Field(min_length=1, max_length=MAX_PASSWORD_BYTES)]
    new_password: Password

    @model_validator(mode="after")
    def _must_differ(self) -> ChangePasswordRequest:
        """A no-op change would still revoke every session, to no purpose."""
        if self.new_password == self.current_password:
            raise ValueError("new_password must differ from current_password")
        return self


class TokenPair(ResponseModel):
    """Newly issued tokens."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = Field(description="Access token lifetime in seconds.")


class UserSummary(ResponseModel):
    """Enough of a user to render their name wherever they are referenced.

    Embedded in incidents, notes, history and escalations because an employee
    cannot call `/api/auth/users`, so a bare id would be unrenderable. Carries
    no email: a reporter's address is not every viewer's business.
    """

    id: uuid.UUID
    full_name: str
    role: Role


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


class EngineerProfileOut(ResponseModel):
    """An engineer's scheduling and skill data."""

    user_id: uuid.UUID
    specialty: str
    max_concurrent_incidents: int
    is_available: bool


class MeOut(UserOut):
    """The caller, as returned by `GET /api/auth/me`."""

    engineer_profile: EngineerProfileOut | None = None


class UserFilters(PageParams):
    """Query parameters for the admin user list."""

    role: Role | None = None
    is_active: bool | None = None
    search: Annotated[str | None, Field(max_length=200)] = None
    sort: Annotated[str, Field(pattern="^(created_at|email|full_name|role)$")] = "created_at"
    order: Order = "desc"


class AdminCreateUserRequest(_CompanyEmail):
    """Admin-only user creation.

    The one place a role may be chosen, which is why it exists separately from
    RegisterRequest rather than as an optional field on it.
    """

    email: EmailStr
    password: Password
    full_name: FullName
    role: Role
    specialty: Specialty | None = None

    @model_validator(mode="after")
    def _specialty_matches_role(self) -> AdminCreateUserRequest:
        """An engineer needs a profile; nobody else may have one.

        Required for an Engineer because the profile is created in the same
        transaction, and an engineer without one cannot be assigned by load.
        Rejected for other roles rather than ignored, so a client mistake is
        visible instead of silently dropped.
        """
        if self.role is Role.ENGINEER and self.specialty is None:
            raise ValueError("specialty is required for an Engineer")
        if self.role is not Role.ENGINEER and self.specialty is not None:
            raise ValueError("specialty applies only to an Engineer")
        return self


class AdminUpdateUserRequest(UpdateModel):
    """Admin-only user update. Omitted fields are unchanged; none may be null.

    `specialty` is needed only when changing a user *to* Engineer who has no
    profile yet. Whether one exists is a database question, so the service
    enforces that rule, not this schema.
    """

    CLEARABLE: ClassVar[frozenset[str]] = frozenset()

    full_name: FullName | None = None
    role: Role | None = None
    is_active: bool | None = None
    specialty: Specialty | None = None
