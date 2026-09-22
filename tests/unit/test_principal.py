"""The authenticated caller, role gates and session revocation."""

from __future__ import annotations

import datetime as dt
import uuid

import pytest

from acme_core.exceptions import Forbidden, Unauthenticated
from acme_core.models.enums import Role
from acme_core.models.user import User
from acme_core.security.principal import (
    Principal,
    ensure_active,
    ensure_session_not_revoked,
    require_admin,
    require_roles,
    require_staff,
)

pytestmark = pytest.mark.unit

NOW = dt.datetime(2026, 6, 1, 12, 0, tzinfo=dt.UTC)


def principal(role: Role = Role.EMPLOYEE) -> Principal:
    return Principal(user_id=uuid.uuid4(), email="a@acme.inc", role=role, is_active=True)


def user(role: Role = Role.EMPLOYEE, **kw: object) -> User:
    return User(
        id=kw.pop("id", uuid.uuid4()),
        email="a@acme.inc",
        full_name="A",
        password_hash="$2b$12$x",
        role=role,
        is_active=kw.pop("is_active", True),
        sessions_valid_from=kw.pop("sessions_valid_from", NOW),
    )


class TestFromUser:
    def test_carries_identity_and_role(self) -> None:
        row = user(Role.ENGINEER)
        built = Principal.from_user(row)
        assert (built.user_id, built.role) == (row.id, Role.ENGINEER)

    def test_role_comes_from_the_row_not_a_claim(self) -> None:
        """A demoted admin must lose access now, not when their token expires."""
        row = user(Role.FACILITY_ADMIN)
        assert Principal.from_user(row).is_admin is True
        row.role = Role.EMPLOYEE
        assert Principal.from_user(row).is_admin is False


class TestRoleProperties:
    @pytest.mark.parametrize(
        ("role", "admin", "staff"),
        [
            (Role.EMPLOYEE, False, False),
            (Role.ENGINEER, False, True),
            (Role.FACILITY_ADMIN, True, True),
        ],
        ids=lambda v: getattr(v, "name", str(v)),
    )
    def test_classification(self, role: Role, admin: bool, staff: bool) -> None:
        p = principal(role)
        assert (p.is_admin, p.is_staff) == (admin, staff)


class TestRoleGates:
    def test_admin_gate_admits_an_admin(self) -> None:
        assert require_admin(principal(Role.FACILITY_ADMIN))

    @pytest.mark.parametrize("role", [Role.EMPLOYEE, Role.ENGINEER], ids=lambda r: r.name)
    def test_admin_gate_rejects_everyone_else(self, role: Role) -> None:
        """Engineers are staff but not administrators; both must be refused."""
        with pytest.raises(Forbidden) as exc:
            require_admin(principal(role))
        assert exc.value.status == 403

    @pytest.mark.parametrize(
        "role", [Role.ENGINEER, Role.FACILITY_ADMIN], ids=lambda r: r.name
    )
    def test_staff_gate_admits_staff(self, role: Role) -> None:
        assert require_staff(principal(role))

    def test_staff_gate_rejects_an_employee(self) -> None:
        with pytest.raises(Forbidden):
            require_staff(principal(Role.EMPLOYEE))

    def test_custom_gate(self) -> None:
        gate = require_roles(Role.ENGINEER)
        assert gate(principal(Role.ENGINEER))
        with pytest.raises(Forbidden):
            gate(principal(Role.FACILITY_ADMIN))

    def test_an_empty_gate_admits_nobody(self) -> None:
        """Fail closed: a gate listing no roles must not become a gate that passes."""
        for role in Role:
            with pytest.raises(Forbidden):
                require_roles()(principal(role))


class TestActiveAccounts:
    def test_an_active_account_passes(self) -> None:
        ensure_active(user())

    def test_a_deactivated_account_is_rejected(self) -> None:
        with pytest.raises(Unauthenticated):
            ensure_active(user(is_active=False))

    def test_deactivation_is_indistinguishable_from_absence(self) -> None:
        """Otherwise the error message becomes an account-existence oracle."""
        with pytest.raises(Unauthenticated) as exc:
            ensure_active(user(is_active=False))
        assert exc.value.message == Unauthenticated.default_message


class TestSessionRevocation:
    def test_a_token_issued_after_the_cutoff_is_accepted(self) -> None:
        ensure_session_not_revoked(user(), NOW + dt.timedelta(minutes=1))

    def test_a_token_issued_before_the_cutoff_is_rejected(self) -> None:
        """This is what makes logout-all and a role change take effect at once."""
        with pytest.raises(Unauthenticated):
            ensure_session_not_revoked(user(), NOW - dt.timedelta(minutes=1))

    def test_a_token_issued_in_the_same_second_is_accepted(self) -> None:
        """`iat` is a whole number of seconds; sub-second drift must not log out."""
        ensure_session_not_revoked(user(), NOW + dt.timedelta(milliseconds=400))

    def test_a_naive_cutoff_is_treated_as_utc(self) -> None:
        """A driver or migration can hand back a naive datetime; comparing it
        against an aware one raises TypeError and 500s every request."""
        row = user(sessions_valid_from=NOW.replace(tzinfo=None))
        ensure_session_not_revoked(row, NOW + dt.timedelta(minutes=1))
