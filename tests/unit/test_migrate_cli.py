"""The migration driver's command line and its lazy-import discipline."""

from __future__ import annotations

import pathlib

import pytest

from acme_core.db import migrate

pytestmark = pytest.mark.unit


@pytest.fixture
def stubbed(monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
    """Replace the Alembic-backed functions so no database is touched."""
    calls: dict[str, object] = {}
    monkeypatch.setattr(migrate, "upgrade_head", lambda: calls.setdefault("upgrade", "abc123"))
    monkeypatch.setattr(
        migrate, "downgrade", lambda target="base": calls.setdefault("downgrade", target) and ""
    )
    monkeypatch.setattr(migrate, "current_revision", lambda: "abc123")
    monkeypatch.setattr(migrate, "migrations_pending", lambda: True)
    return calls


class TestCommandDispatch:
    def test_upgrade_is_the_default(
        self, stubbed: dict[str, object], capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert migrate.main([]) == 0
        assert "abc123" in capsys.readouterr().out

    def test_upgrade(self, stubbed: dict[str, object]) -> None:
        assert migrate.main(["upgrade"]) == 0
        assert stubbed["upgrade"] == "abc123"

    def test_downgrade_defaults_to_base(self, stubbed: dict[str, object]) -> None:
        assert migrate.main(["downgrade"]) == 0
        assert stubbed["downgrade"] == "base"

    def test_downgrade_accepts_a_target(self, stubbed: dict[str, object]) -> None:
        assert migrate.main(["downgrade", "abc123"]) == 0
        assert stubbed["downgrade"] == "abc123"

    def test_current(
        self, stubbed: dict[str, object], capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert migrate.main(["current"]) == 0
        assert capsys.readouterr().out.strip() == "abc123"

    def test_pending(
        self, stubbed: dict[str, object], capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert migrate.main(["pending"]) == 0
        assert capsys.readouterr().out.strip() == "yes"

    def test_unknown_action_exits_non_zero(
        self, stubbed: dict[str, object], capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert migrate.main(["frobnicate"]) == 2
        assert "unknown action" in capsys.readouterr().err

    def test_current_reports_none_when_unmigrated(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(migrate, "current_revision", lambda: None)
        assert migrate.main(["current"]) == 0
        assert capsys.readouterr().out.strip() == "none"


class TestScriptLocation:
    def test_resolves_inside_the_package(self) -> None:
        """Must survive the rsync into a service directory, where no ini exists."""
        assert migrate._SCRIPT_LOCATION.name == "migrations"
        assert (migrate._SCRIPT_LOCATION / "env.py").is_file()

    def test_alembic_is_not_imported_at_module_scope(self) -> None:
        """Alembic drags in Mako and MarkupSafe; the request path never needs them.

        A 128 MB Lambda (infra/lambda.tf:11) cannot spare them on the ASGI path.
        """
        source = pathlib.Path(migrate.__file__ or "").read_text()
        module_level = [
            line
            for line in source.splitlines()
            if line.startswith(("import alembic", "from alembic"))
        ]
        assert module_level == []
