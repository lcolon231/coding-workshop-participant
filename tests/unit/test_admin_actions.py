"""Admin action dispatch and its refusals, without a database."""

from __future__ import annotations

from typing import Any

import pytest

from acme_core import admin_actions
from acme_core.admin_actions import AdminActionRefused, run_admin_action

pytestmark = pytest.mark.unit


class TestSeedRefusals:
    """Every refusal happens before a session is opened -- the unit guard proves it."""

    def test_without_app_id_in_the_environment(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("APP_ID", raising=False)
        with pytest.raises(AdminActionRefused, match="confirm"):
            run_admin_action("seed", {"confirm": "", "admin_password": "x" * 16})

    @pytest.mark.parametrize("confirm", [None, "", "someone-else", 123])
    def test_with_the_wrong_confirmation(
        self, monkeypatch: pytest.MonkeyPatch, confirm: object
    ) -> None:
        monkeypatch.setenv("APP_ID", "app-123")
        with pytest.raises(AdminActionRefused, match="confirm"):
            run_admin_action("seed", {"confirm": confirm, "admin_password": "x" * 16})

    @pytest.mark.parametrize("password", [None, "", 42])
    def test_without_a_password(self, monkeypatch: pytest.MonkeyPatch, password: object) -> None:
        monkeypatch.setenv("APP_ID", "app-123")
        with pytest.raises(AdminActionRefused, match="admin_password"):
            run_admin_action("seed", {"confirm": "app-123", "admin_password": password})

    def test_a_refusal_never_echoes_the_password(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("APP_ID", "app-123")
        with pytest.raises(AdminActionRefused) as exc:
            run_admin_action("seed", {"confirm": "wrong", "admin_password": "masked-value-123"})
        assert "masked-value-123" not in str(exc.value)


class TestMigrate:
    def test_upgrades_then_drops_the_pool(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The next request must not reuse a connection opened on the old schema."""
        calls: list[str] = []
        from acme_core.db import engine, migrate

        monkeypatch.setattr(migrate, "upgrade_head", lambda: calls.append("upgrade") or "0001")
        monkeypatch.setattr(engine, "dispose_engine", lambda: calls.append("dispose"))
        result = run_admin_action("migrate", {})
        assert calls == ["upgrade", "dispose"]
        assert result == {"action": "migrate", "ok": True, "revision": "0001"}


class TestDispatch:
    def test_an_unknown_action_is_refused(self) -> None:
        """Unreachable through classify(); kept so the function is safe on its own."""
        with pytest.raises(ValueError, match="unknown admin action"):
            run_admin_action("drop-everything", {})

    def test_options_are_never_logged(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        monkeypatch.setattr(admin_actions, "_db_current", lambda: {"ok": True})
        run_admin_action("db-current", {"admin_password": "masked-value-123"})
        assert "masked-value-123" not in caplog.text


class TestSeedCli:
    def test_refuses_to_run_without_a_password(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from acme_core import seed

        monkeypatch.delenv(seed.PASSWORD_ENV, raising=False)
        assert seed.main() == 2
        assert seed.PASSWORD_ENV in capsys.readouterr().err

    def test_seeds_and_commits_with_a_password(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from acme_core import seed
        from acme_core.db import engine

        committed: list[bool] = []

        class FakeSession:
            def __enter__(self) -> FakeSession:
                return self

            def __exit__(self, *_: Any) -> None:
                return None

            def commit(self) -> None:
                committed.append(True)

        monkeypatch.setenv(seed.PASSWORD_ENV, "a-demo-passphrase")
        monkeypatch.setattr(engine, "get_session_factory", lambda: FakeSession)
        monkeypatch.setattr(seed, "seed", lambda _s, _p: {"users_created": 5})
        assert seed.main() == 0
        assert committed == [True]
        assert "users_created" in capsys.readouterr().out
