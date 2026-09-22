"""Every query the auth service runs.

No `session.get()` on a child and no bare `update()` / `delete()` (S6): rows are
selected, then changed as ORM objects, so each mutation is visible in one place
and nothing bypasses the unit of work.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from acme_core.models.enums import IncidentStatus
from acme_core.models.incident import Incident
from acme_core.models.user import EngineerProfile, RefreshToken, User
from acme_core.pagination import like_pattern, paginate
from acme_core.schemas.auth import UserFilters

_USER_SORTS = {
    "created_at": User.created_at,
    "email": User.email,
    "full_name": User.full_name,
    "role": User.role,
}


def get_user(session: Session, user_id: uuid.UUID) -> User | None:
    """Fetch a user by primary key. Users are top-level rows, not children."""
    return session.get(User, user_id)


def get_user_by_email(session: Session, email: str) -> User | None:
    """Fetch a user by (already normalised) email."""
    return session.execute(select(User).where(User.email == email)).scalar_one_or_none()


def get_user_for_update(session: Session, user_id: uuid.UUID) -> User | None:
    """Fetch and lock a user, so concurrent admin edits serialise."""
    return session.execute(
        select(User).where(User.id == user_id).with_for_update()
    ).scalar_one_or_none()


def list_users(session: Session, filters: UserFilters) -> tuple[list[User], int]:
    """Page through users with the admin list's filters."""
    statement: Select[Any] = select(User)
    if filters.role is not None:
        statement = statement.where(User.role == filters.role)
    if filters.is_active is not None:
        statement = statement.where(User.is_active.is_(filters.is_active))
    if filters.search:
        pattern = like_pattern(filters.search.lower())
        statement = statement.where(
            or_(
                User.email.ilike(pattern, escape="\\"),
                User.full_name.ilike(pattern, escape="\\"),
            )
        )
    return paginate(
        session,
        statement,
        filters,
        sort_columns=_USER_SORTS,
        sort=filters.sort,
        order=filters.order,
        tiebreaker=User.id,
    )


def get_engineer_profile(session: Session, user_id: uuid.UUID) -> EngineerProfile | None:
    """Fetch a user's engineer profile through its unique user_id."""
    return session.execute(
        select(EngineerProfile).where(EngineerProfile.user_id == user_id)
    ).scalar_one_or_none()


def count_open_assignments(session: Session, user_id: uuid.UUID) -> int:
    """Count non-closed incidents assigned to a user."""
    return session.execute(
        select(func.count())
        .select_from(Incident)
        .where(Incident.assignee_id == user_id, Incident.status != IncidentStatus.CLOSED)
    ).scalar_one()


def get_refresh_token_for_update(session: Session, token_hash: str) -> RefreshToken | None:
    """Fetch and lock a refresh token by its hash.

    Locked so two concurrent refreshes with the same token serialise: the
    second sees `revoked_at` set by the first and is treated as reuse, rather
    than both succeeding and forking the family.
    """
    return session.execute(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash).with_for_update()
    ).scalar_one_or_none()


def live_tokens_in_family(session: Session, family_id: uuid.UUID) -> Sequence[RefreshToken]:
    """Every unrevoked token in one family."""
    return (
        session.execute(
            select(RefreshToken).where(
                RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None)
            )
        )
        .scalars()
        .all()
    )


def live_tokens_for_user(session: Session, user_id: uuid.UUID) -> Sequence[RefreshToken]:
    """Every unrevoked token a user holds, across all devices."""
    return (
        session.execute(
            select(RefreshToken).where(
                RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None)
            )
        )
        .scalars()
        .all()
    )


def revoke(tokens: Sequence[RefreshToken], now: dt.datetime) -> None:
    """Mark tokens revoked. The session flushes them with the request."""
    for token in tokens:
        token.revoked_at = now
