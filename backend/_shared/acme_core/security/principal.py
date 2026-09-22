"""The authenticated caller.

Built from the database row rather than from token claims. A JWT proves
identity; it must never be the source of authority. Reading `role` from a
claim means a demoted admin keeps administrative access until their access
token expires -- up to thirty minutes after the decision to remove it.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from acme_core.exceptions import Forbidden, Unauthenticated
from acme_core.models.enums import Role

if TYPE_CHECKING:
    from acme_core.models.user import User

# Roles that may read internal notes and see incidents they neither reported
# nor were assigned.
STAFF_ROLES = frozenset({Role.FACILITY_ADMIN, Role.ENGINEER})


@dataclass(frozen=True, slots=True)
class Principal:
    """Who is making this request, and what they may do."""

    user_id: uuid.UUID
    email: str
    role: Role
    is_active: bool

    @property
    def is_admin(self) -> bool:
        """Whether this caller administers the platform."""
        return self.role is Role.FACILITY_ADMIN

    @property
    def is_staff(self) -> bool:
        """Whether this caller may see other people's incidents and internal notes."""
        return self.role in STAFF_ROLES

    @classmethod
    def from_user(cls, user: User) -> Principal:
        """Build a principal from a database row.

        Args:
            user: The persisted user.

        Returns:
            The principal for this request.
        """
        return cls(
            user_id=user.id,
            email=user.email,
            role=user.role,
            is_active=user.is_active,
        )


def ensure_active(user: User) -> None:
    """Reject a deactivated account.

    Args:
        user: The persisted user.

    Raises:
        Unauthenticated: The account has been deactivated.
    """
    if not user.is_active:
        # Deliberately the same error a missing account produces: a deactivated
        # account should not be distinguishable from one that never existed.
        raise Unauthenticated("Authentication required.")


def ensure_session_not_revoked(user: User, token_issued_at: dt.datetime) -> None:
    """Reject a token issued before the user's sessions were invalidated.

    `sessions_valid_from` is bumped on logout-all, password change, role change
    and deactivation, which is what makes those take effect immediately rather
    than whenever the access token happens to expire.

    Args:
        user: The persisted user.
        token_issued_at: The token's `iat`.

    Raises:
        Unauthenticated: The token predates the cutoff.
    """
    cutoff = user.sessions_valid_from
    if cutoff.tzinfo is None:
        cutoff = cutoff.replace(tzinfo=dt.UTC)
    # Whole-second comparison: `iat` is stored as an integer, so a token issued
    # in the same second as the cutoff must not be rejected by sub-second drift.
    if int(token_issued_at.timestamp()) < int(cutoff.timestamp()):
        raise Unauthenticated("Session has been revoked; sign in again.")


def require_roles(*roles: Role) -> Callable[[Principal], Principal]:
    """Build a check that admits only the given roles.

    Args:
        roles: The roles permitted at this endpoint.

    Returns:
        A callable that returns the principal or raises.
    """
    permitted = frozenset(roles)

    def _check(principal: Principal) -> Principal:
        if principal.role not in permitted:
            raise Forbidden("You do not have permission to perform this action.")
        return principal

    return _check


def require_admin(principal: Principal) -> Principal:
    """Admit only Facility Admins.

    Args:
        principal: The authenticated caller.

    Returns:
        The same principal.

    Raises:
        Forbidden: The caller is not an admin.
    """
    return require_roles(Role.FACILITY_ADMIN)(principal)


def require_staff(principal: Principal) -> Principal:
    """Admit Facility Admins and Engineers.

    Args:
        principal: The authenticated caller.

    Returns:
        The same principal.

    Raises:
        Forbidden: The caller is not staff.
    """
    return require_roles(*STAFF_ROLES)(principal)
