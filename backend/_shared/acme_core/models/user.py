"""Users, engineer profiles and refresh tokens.

Note the deliberate absence of `from __future__ import annotations` in the
model modules: stringised annotations interact badly with SQLAlchemy 2.0's
`Mapped[...]` resolution, which evaluates them at class-creation time.
"""

import datetime as dt
import uuid
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from acme_core.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from acme_core.models.enums import Role
from acme_core.models.types import enum_type

if TYPE_CHECKING:
    from acme_core.models.incident import Incident


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A person who can sign in.

    Self-registration always creates an `EMPLOYEE`; Engineer and Facility Admin
    accounts are created through the admin endpoint, so possessing a company
    email address cannot by itself confer privilege.
    """

    __tablename__ = "users"

    # Stored already lower-cased so the unique constraint is genuinely
    # case-insensitive without needing citext or a functional index.
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    role: Mapped[Role] = mapped_column(
        enum_type(Role), nullable=False, default=Role.EMPLOYEE
    )

    # Only an Employee has one; the service clears it when the role changes
    # away from Employee, so the rule "occupation iff Employee" holds for every
    # row the API writes. Nullable in the database for the other roles.
    occupation: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    # Required by the API for every new or edited user, and never in the
    # future. Nullable in the database only because rows created before this
    # column existed have no value to backfill -- inventing one would be a data
    # lie. Tighten to NOT NULL once every existing row has been given a date.
    date_of_birth: Mapped[Optional[dt.date]] = mapped_column(Date, nullable=True)
    # Soft delete. A hard delete would either orphan or cascade away the
    # incident history that references this user as reporter or assignee.
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Access tokens issued before this instant are rejected. Bumped on logout-all,
    # password change, role change and deactivation, which is what makes a
    # demoted admin lose privilege immediately rather than up to 30 minutes later.
    sessions_valid_from: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # Account-based lockout. Deliberately not IP-based: on the Function URL the
    # caller controls X-Forwarded-For, and through CloudFront the source address
    # is an edge node, so an IP counter is bypassable by construction.
    failed_login_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    locked_until: Mapped[Optional[dt.datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    engineer_profile: Mapped[Optional["EngineerProfile"]] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    refresh_tokens: Mapped[list["RefreshToken"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    reported_incidents: Mapped[list["Incident"]] = relationship(
        back_populates="reporter", foreign_keys="Incident.reporter_id"
    )
    assigned_incidents: Mapped[list["Incident"]] = relationship(
        back_populates="assignee", foreign_keys="Incident.assignee_id"
    )

    def __repr__(self) -> str:
        """Return a representation that never contains the password hash."""
        return f"<User {self.email!r} role={self.role!r} active={self.is_active!r}>"


class EngineerProfile(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Scheduling and skill data for a user with the Engineer role."""

    __tablename__ = "engineer_profiles"

    # Unique, which is what makes this one-to-one rather than one-to-many.
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    specialty: Mapped[str] = mapped_column(String(100), nullable=False)
    max_concurrent_incidents: Mapped[int] = mapped_column(
        Integer, nullable=False, default=5
    )
    is_available: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    user: Mapped["User"] = relationship(back_populates="engineer_profile")

    def __repr__(self) -> str:
        """Return a short representation."""
        return f"<EngineerProfile user={self.user_id} specialty={self.specialty!r}>"


class RefreshToken(UUIDPrimaryKeyMixin, Base):
    """A hashed, rotatable refresh token.

    Only the hash is stored: a database disclosure must not yield usable
    credentials. Rotation issues a new row in the same `family_id`; presenting
    an already-rotated token means the token was copied, so the whole family is
    revoked rather than just that row.
    """

    __tablename__ = "refresh_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    family_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    issued_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    expires_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    revoked_at: Mapped[Optional[dt.datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    user: Mapped["User"] = relationship(back_populates="refresh_tokens")

    __table_args__ = (
        # Revoking a family on reuse reads every row for that family.
        Index("ix_refresh_tokens_family_id", "family_id"),
        Index("ix_refresh_tokens_user_id", "user_id"),
    )

    def __repr__(self) -> str:
        """Return a representation that never contains the token hash."""
        return f"<RefreshToken user={self.user_id} family={self.family_id} revoked={bool(self.revoked_at)}>"


class AppSecret(TimestampMixin, Base):
    """A server-generated secret, persisted so it survives cold starts.

    Exists because no Lambda environment variable can be added without editing
    Terraform, and the obvious alternative -- deriving a key from POSTGRES_PASS
    -- is unsound: infra/rds.tf:15 sets the Aurora password to a three-word
    `random_pet` value, roughly 2**30 candidates and brute-forceable offline
    against any issued token. The JWT signing key is 32 random bytes written
    here on first use.
    """

    __tablename__ = "app_secrets"

    name: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(String(512), nullable=False)

    def __repr__(self) -> str:
        """Return a representation that never contains the secret value."""
        return f"<AppSecret {self.name!r}>"
