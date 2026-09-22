"""The demo seed and the admin action that runs it, against a real database."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from sqlalchemy import Connection, func, select
from sqlalchemy.orm import Session

from acme_core import admin_actions
from acme_core.db import engine as engine_module
from acme_core.exceptions import ValidationFailed
from acme_core.models import (
    Building,
    Category,
    EngineerProfile,
    Floor,
    Incident,
    IncidentStatus,
    IncidentStatusHistory,
    Role,
    Seat,
    User,
)
from acme_core.security.passwords import verify_password
from acme_core.seed import SEED_BUILDINGS, SEED_CATEGORIES, SEED_INCIDENTS, SEED_USERS, seed
from acme_core.workflow import TRANSITIONS

pytestmark = pytest.mark.integration

DEMO_PASSWORD = "a-demo-passphrase-for-tests"


def user_count(session: Session) -> int:
    return count(session, User)


def count(session: Session, model: Any) -> int:
    return session.execute(select(func.count()).select_from(model)).scalar_one()


FACILITY_ROWS = sum(1 + sum(1 + len(f.seats) for f in b.floors) for b in SEED_BUILDINGS)
CATEGORY_ROWS = sum(1 + len(children) for children in SEED_CATEGORIES.values())


class TestSeed:
    def test_creates_every_demo_account(self, db_session: Session, verify_session: Session) -> None:
        report = seed(db_session, DEMO_PASSWORD)
        db_session.commit()
        assert (report["users_created"], report["users_existing"]) == (len(SEED_USERS), 0)
        assert user_count(verify_session) == len(SEED_USERS)

    def test_creates_the_facilities_and_categories(
        self, db_session: Session, verify_session: Session
    ) -> None:
        report = seed(db_session, DEMO_PASSWORD)
        db_session.commit()
        assert report["facilities_created"] == FACILITY_ROWS
        assert report["categories_created"] == CATEGORY_ROWS
        assert count(verify_session, Building) == len(SEED_BUILDINGS)
        assert count(verify_session, Floor) + count(verify_session, Seat) == (
            FACILITY_ROWS - len(SEED_BUILDINGS)
        )
        parents = verify_session.scalars(select(Category).where(Category.parent_id.is_(None)))
        assert {c.name for c in parents} == set(SEED_CATEGORIES)

    def test_creates_incidents_with_legal_histories(
        self, db_session: Session, verify_session: Session
    ) -> None:
        """Every history is a chain of real edges ending at the stored status."""
        report = seed(db_session, DEMO_PASSWORD)
        db_session.commit()
        assert report["incidents_created"] == len(SEED_INCIDENTS)
        edges = {(rule.source, rule.target) for rule in TRANSITIONS}
        for incident in verify_session.scalars(select(Incident)).all():
            rows = verify_session.scalars(
                select(IncidentStatusHistory)
                .where(IncidentStatusHistory.incident_id == incident.id)
                .order_by(IncidentStatusHistory.created_at)
            ).all()
            assert (rows[0].from_status, rows[0].to_status) == (None, IncidentStatus.OPEN)
            assert all((r.from_status, r.to_status) in edges for r in rows[1:])
            assert rows[-1].to_status is incident.status
            assert incident.created_at == rows[0].created_at
        statuses = {i.status for i in verify_session.scalars(select(Incident))}
        assert statuses == set(IncidentStatus)

    def test_stamps_follow_the_workflow_policy(
        self, db_session: Session, verify_session: Session
    ) -> None:
        seed(db_session, DEMO_PASSWORD)
        db_session.commit()
        for incident in verify_session.scalars(select(Incident)).all():
            started = incident.status is not IncidentStatus.OPEN and incident.assignee_id
            assert (incident.acknowledged_at is not None) == bool(started)
            assert (incident.closed_at is not None) == (incident.status is IncidentStatus.CLOSED)
            if incident.status is IncidentStatus.BLOCKED:
                assert incident.blocked_reason

    def test_covers_every_role(self, db_session: Session, verify_session: Session) -> None:
        seed(db_session, DEMO_PASSWORD)
        db_session.commit()
        roles = set(verify_session.execute(select(User.role)).scalars())
        assert roles == set(Role)

    def test_engineers_get_profiles(self, db_session: Session, verify_session: Session) -> None:
        seed(db_session, DEMO_PASSWORD)
        db_session.commit()
        engineers = sum(1 for u in SEED_USERS if u.role is Role.ENGINEER)
        profiles = verify_session.execute(
            select(func.count()).select_from(EngineerProfile)
        ).scalar_one()
        assert profiles == engineers

    def test_uses_the_supplied_password(self, db_session: Session, verify_session: Session) -> None:
        seed(db_session, DEMO_PASSWORD)
        db_session.commit()
        admin = verify_session.execute(
            select(User).where(User.email == "admin@acme.inc")
        ).scalar_one()
        assert verify_password(DEMO_PASSWORD, admin.password_hash)

    def test_is_idempotent(self, db_session: Session, verify_session: Session) -> None:
        seed(db_session, DEMO_PASSWORD)
        db_session.commit()
        report = seed(db_session, DEMO_PASSWORD)
        db_session.commit()
        assert {k: v for k, v in report.items() if k.endswith("_created")} == {
            "users_created": 0, "facilities_created": 0,
            "categories_created": 0, "incidents_created": 0,
        }
        assert report["users_existing"] == len(SEED_USERS)
        assert report["incidents_existing"] == len(SEED_INCIDENTS)
        assert user_count(verify_session) == len(SEED_USERS)
        assert count(verify_session, Incident) == len(SEED_INCIDENTS)

    def test_is_strictly_additive(self, db_session: Session, verify_session: Session) -> None:
        """Re-seeding must not undo an admin's changes or reset a chosen password."""
        seed(db_session, DEMO_PASSWORD)
        db_session.commit()
        admin = db_session.execute(select(User).where(User.email == "admin@acme.inc")).scalar_one()
        admin.role = Role.EMPLOYEE
        db_session.commit()

        incident = db_session.scalars(select(Incident)).first()
        assert incident is not None
        incident.title = "Renamed by an admin"
        db_session.commit()

        seed(db_session, "a-different-passphrase")
        db_session.commit()
        again = verify_session.get(User, admin.id, populate_existing=True)
        assert again is not None and again.role is Role.EMPLOYEE
        assert verify_password(DEMO_PASSWORD, again.password_hash)
        renamed = verify_session.get(Incident, incident.id, populate_existing=True)
        assert renamed is not None and renamed.title == "Renamed by an admin"

    def test_incidents_follow_an_account_registered_first(
        self, db_session: Session, make_user: Any, verify_session: Session
    ) -> None:
        """A reporter who registered before the seed keeps their id; incidents use it."""
        registered = make_user(email="employee@acme.inc")
        seed(db_session, DEMO_PASSWORD)
        db_session.commit()
        reporters = set(verify_session.scalars(select(Incident.reporter_id)))
        assert registered.id in reporters

    def test_skips_an_address_someone_registered_first(
        self, db_session: Session, make_user: Any
    ) -> None:
        make_user(email="employee@acme.inc")
        report = seed(db_session, DEMO_PASSWORD)
        assert report["users_existing"] == 1

    def test_refuses_a_weak_password(self, db_session: Session) -> None:
        with pytest.raises(ValidationFailed):
            seed(db_session, "admin")


@pytest.fixture
def isolated_session_factory(
    connection: Connection, monkeypatch: pytest.MonkeyPatch
) -> Callable[[], Session]:
    """Make the admin action's own session join the test transaction.

    The action opens a session and commits it. Unpatched, that commit would
    be real, and the seeded users would leak into every later test.
    """

    def factory() -> Session:
        return Session(bind=connection, join_transaction_mode="create_savepoint")

    monkeypatch.setattr(engine_module, "get_session_factory", lambda: factory)
    return factory


class TestSeedAction:
    def test_seeds_with_matching_confirmation(
        self,
        monkeypatch: pytest.MonkeyPatch,
        isolated_session_factory: Any,
        verify_session: Session,
    ) -> None:
        monkeypatch.setenv("APP_ID", "app-123")
        result = admin_actions.run_admin_action(
            "seed", {"confirm": "app-123", "admin_password": DEMO_PASSWORD}
        )
        assert result["ok"] is True and result["users_created"] == len(SEED_USERS)
        assert user_count(verify_session) == len(SEED_USERS)

    def test_the_result_never_echoes_the_password(
        self, monkeypatch: pytest.MonkeyPatch, isolated_session_factory: Any
    ) -> None:
        monkeypatch.setenv("APP_ID", "app-123")
        result = admin_actions.run_admin_action(
            "seed", {"confirm": "app-123", "admin_password": DEMO_PASSWORD}
        )
        assert DEMO_PASSWORD not in repr(result)

    def test_db_current_reports_head(self) -> None:
        result = admin_actions.run_admin_action("db-current", {})
        assert result["ok"] is True and result["pending"] is False
        assert result["revision"]
