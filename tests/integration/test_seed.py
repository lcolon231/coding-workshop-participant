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
from acme_core.models import EngineerProfile, Role, User
from acme_core.security.passwords import verify_password
from acme_core.seed import SEED_USERS, seed

pytestmark = pytest.mark.integration

DEMO_PASSWORD = "a-demo-passphrase-for-tests"


def user_count(session: Session) -> int:
    return session.execute(select(func.count()).select_from(User)).scalar_one()


class TestSeed:
    def test_creates_every_demo_account(self, db_session: Session, verify_session: Session) -> None:
        report = seed(db_session, DEMO_PASSWORD)
        db_session.commit()
        assert report == {"users_created": len(SEED_USERS), "users_existing": 0}
        assert user_count(verify_session) == len(SEED_USERS)

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
        assert report == {"users_created": 0, "users_existing": len(SEED_USERS)}
        assert user_count(verify_session) == len(SEED_USERS)

    def test_is_strictly_additive(self, db_session: Session, verify_session: Session) -> None:
        """Re-seeding must not undo an admin's changes or reset a chosen password."""
        seed(db_session, DEMO_PASSWORD)
        db_session.commit()
        admin = db_session.execute(select(User).where(User.email == "admin@acme.inc")).scalar_one()
        admin.role = Role.EMPLOYEE
        db_session.commit()

        seed(db_session, "a-different-passphrase")
        db_session.commit()
        again = verify_session.get(User, admin.id, populate_existing=True)
        assert again is not None and again.role is Role.EMPLOYEE
        assert verify_password(DEMO_PASSWORD, again.password_hash)

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
