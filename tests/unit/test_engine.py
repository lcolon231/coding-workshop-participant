"""Lazy engine construction, memoisation and session lifecycle.

These run without a database: `create_engine` is replaced by a recorder, so
what is under test is our construction logic, not SQLAlchemy's connectivity.
"""

from __future__ import annotations

from typing import Any

import pytest

from acme_core.config import get_settings
from acme_core.db import engine as engine_module

pytestmark = pytest.mark.unit


class _FakeEngine:
    """Stands in for a SQLAlchemy Engine, recording disposal."""

    def __init__(self, url: str, **kwargs: Any) -> None:
        self.url = url
        self.kwargs = kwargs
        self.disposed = False

    def dispose(self) -> None:
        self.disposed = True


@pytest.fixture
def recorder(monkeypatch: pytest.MonkeyPatch) -> list[_FakeEngine]:
    """Replace create_engine with a recorder, overriding the no-DB guard."""
    built: list[_FakeEngine] = []

    def _fake(url: str, **kwargs: Any) -> _FakeEngine:
        built.append(_FakeEngine(url, **kwargs))
        return built[-1]

    monkeypatch.setattr(engine_module, "create_engine", _fake)
    engine_module.dispose_engine()
    return built


class TestLaziness:
    def test_importing_does_not_build_an_engine(self, recorder: list[_FakeEngine]) -> None:
        """Cold starts must not pay for a pool that may never be used."""
        assert recorder == []

    def test_built_on_first_use(self, recorder: list[_FakeEngine]) -> None:
        engine_module.get_engine()
        assert len(recorder) == 1

    def test_memoised(self, recorder: list[_FakeEngine]) -> None:
        assert engine_module.get_engine() is engine_module.get_engine()
        assert len(recorder) == 1


class TestPoolConfiguration:
    def test_pool_is_minimal(self, recorder: list[_FakeEngine]) -> None:
        """One request per execution environment: a second connection is waste."""
        engine_module.get_engine()
        assert recorder[0].kwargs["pool_size"] == 1
        assert recorder[0].kwargs["max_overflow"] == 0

    def test_pre_ping_enabled(self, recorder: list[_FakeEngine]) -> None:
        """Aurora scales to zero capacity and drops idle connections."""
        engine_module.get_engine()
        assert recorder[0].kwargs["pool_pre_ping"] is True

    def test_recycle_below_common_idle_timeout(self, recorder: list[_FakeEngine]) -> None:
        engine_module.get_engine()
        assert 0 < recorder[0].kwargs["pool_recycle"] < 300

    def test_pool_timeout_fails_fast(self, recorder: list[_FakeEngine]) -> None:
        """Beats SQLAlchemy's 30s default, which outlives most request deadlines."""
        engine_module.get_engine()
        assert recorder[0].kwargs["pool_timeout"] == 5

    def test_url_comes_from_settings(self, recorder: list[_FakeEngine]) -> None:
        engine_module.get_engine()
        assert recorder[0].url == get_settings().database_url


class TestDisposal:
    def test_dispose_releases_and_resets(self, recorder: list[_FakeEngine]) -> None:
        first = engine_module.get_engine()
        engine_module.dispose_engine()
        assert first.disposed is True
        assert engine_module.get_engine() is not first
        assert len(recorder) == 2

    def test_dispose_is_safe_when_never_built(self, recorder: list[_FakeEngine]) -> None:
        engine_module.dispose_engine()
        engine_module.dispose_engine()
        assert recorder == []

    def test_dispose_also_resets_the_session_factory(
        self, recorder: list[_FakeEngine], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A factory bound to a disposed engine would hand out dead sessions."""
        monkeypatch.setattr(engine_module, "sessionmaker", lambda **kw: object())
        first = engine_module.get_session_factory()
        engine_module.dispose_engine()
        assert engine_module.get_session_factory() is not first


class TestGuardFixture:
    def test_unit_tier_cannot_build_a_real_engine(self) -> None:
        """The autouse guard is what makes 'no I/O' enforced, not merely intended.

        This test does NOT request the recorder fixture, so the guard is active.
        """
        with pytest.raises(AssertionError, match="must not construct a database engine"):
            engine_module.get_engine()


class TestGetDb:
    """The FastAPI dependency.

    Every integration test replaces this via dependency_overrides, so without
    direct tests its body never executes and the module that matters most is
    also the least measured.
    """

    @pytest.fixture
    def session_spy(self, monkeypatch: pytest.MonkeyPatch) -> dict[str, list[str]]:
        calls: dict[str, list[str]] = {"events": []}

        class _FakeSession:
            def commit(self) -> None:
                calls["events"].append("commit")

            def rollback(self) -> None:
                calls["events"].append("rollback")

            def close(self) -> None:
                calls["events"].append("close")

        monkeypatch.setattr(engine_module, "get_session_factory", lambda: _FakeSession)
        return calls

    def test_commits_on_success(self, session_spy: dict[str, list[str]]) -> None:
        for _ in engine_module.get_db():
            pass
        assert session_spy["events"] == ["commit", "close"]

    def test_rolls_back_and_reraises(self, session_spy: dict[str, list[str]]) -> None:
        gen = engine_module.get_db()
        next(gen)
        with pytest.raises(ValueError, match="boom"):
            gen.throw(ValueError("boom"))
        assert session_spy["events"] == ["rollback", "close"]

    def test_always_closes(self, session_spy: dict[str, list[str]]) -> None:
        """A leaked session holds a pooled connection; the pool has exactly one."""
        gen = engine_module.get_db()
        next(gen)
        with pytest.raises(ValueError):
            gen.throw(ValueError())
        assert session_spy["events"][-1] == "close"
