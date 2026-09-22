"""Declarative base and shared column mixins.

The naming convention is set on the MetaData rather than left to PostgreSQL's
defaults so that Alembic autogenerate produces stable, explicit names for
indexes and constraints. Without it, autogenerate cannot reliably emit a
`drop_constraint` for a constraint the database named itself, and downgrades
break in ways that only show up when you need them.
"""

from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import MetaData, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_name)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Declarative base for every ACME model."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class UUIDPrimaryKeyMixin:
    """Adds a client-generatable UUID primary key.

    UUIDs rather than serial integers so the seed can derive deterministic ids
    with uuid5 and stay idempotent across runs, and so ids are not guessable by
    enumeration.
    """

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )


class TimestampMixin:
    """Adds server-side created/updated timestamps.

    Defaults are server-side (`now()`) so rows written outside the ORM -- by a
    migration or by the seed's bulk paths -- are stamped consistently.
    """

    created_at: Mapped[dt.datetime] = mapped_column(
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
