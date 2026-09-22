"""Provisioning the JWT signing key in the database."""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from acme_core.models import AppSecret
from acme_core.security import secret as secret_module
from acme_core.security.secret import SECRET_NAME, get_jwt_secret, reset_cache

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _clear_cache() -> None:
    reset_cache()


class TestProvisioning:
    def test_creates_a_secret_on_first_use(self, db_session: Session) -> None:
        value = get_jwt_secret(db_session)
        assert value
        assert db_session.get(AppSecret, SECRET_NAME) is not None

    def test_has_real_entropy(self, db_session: Session) -> None:
        """The whole reason this exists rather than deriving from POSTGRES_PASS,
        which infra/rds.tf sets to a three-word random_pet value."""
        assert len(get_jwt_secret(db_session)) >= 32

    def test_is_stable_across_calls(self, db_session: Session) -> None:
        """A key that changed per call would invalidate every issued token."""
        first = get_jwt_secret(db_session)
        reset_cache()
        assert get_jwt_secret(db_session) == first

    def test_is_cached_after_the_first_read(
        self, db_session: Session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """One query per cold start, not one per request."""
        get_jwt_secret(db_session)
        calls = {"n": 0}

        def _counted(session: Session) -> str | None:
            calls["n"] += 1
            return "should-not-be-read"

        monkeypatch.setattr(secret_module, "_read", _counted)
        get_jwt_secret(db_session)
        assert calls["n"] == 0

    def test_an_existing_secret_is_reused_not_replaced(
        self, db_session: Session
    ) -> None:
        """A second cold start must adopt the first one's key."""
        db_session.execute(
            text(
                "INSERT INTO app_secrets (name, value, created_at, updated_at) "
                "VALUES (:n, :v, now(), now())"
            ),
            {"n": SECRET_NAME, "v": "pre-existing-secret-value"},
        )
        db_session.commit()
        assert get_jwt_secret(db_session) == "pre-existing-secret-value"

    def test_concurrent_provisioning_converges(self, db_session: Session) -> None:
        """Two cold Lambdas can reach this together; the loser must take the
        winner's key, not keep its own. ON CONFLICT DO NOTHING then re-read."""
        first = get_jwt_secret(db_session)
        reset_cache()
        second = get_jwt_secret(db_session)
        assert first == second
        count = db_session.execute(
            text("SELECT count(*) FROM app_secrets WHERE name = :n"), {"n": SECRET_NAME}
        ).scalar_one()
        assert count == 1


class TestSecrecy:
    def test_the_secret_is_never_in_a_repr(self, db_session: Session) -> None:
        get_jwt_secret(db_session)
        row = db_session.get(AppSecret, SECRET_NAME)
        assert row is not None
        assert row.value not in repr(row)

    def test_tokens_signed_with_it_verify(self, db_session: Session) -> None:
        """End to end: the provisioned key actually works for its purpose."""
        import uuid

        from acme_core.security.tokens import TokenType, decode_token, issue_token

        key = get_jwt_secret(db_session)
        user = uuid.uuid4()
        token, _ = issue_token(user, TokenType.ACCESS, key)
        assert decode_token(token, key, expected_type=TokenType.ACCESS).subject == user
