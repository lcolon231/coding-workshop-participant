"""Fixtures enforcing that the unit tier performs no I/O.

"Unit tests do not touch a database" is otherwise only a convention, and the
lazy module-global engine makes breaking it silent rather than loud: any code
that opens its own session bypasses FastAPI's dependency overrides entirely and
connects to whatever the environment points at -- on this VDI, a real
PostgreSQL that exists and accepts writes. Tests would pass while mutating the
developer's database.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any, NoReturn

import pytest


@pytest.fixture(autouse=True)
def _no_database(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Make engine construction raise for the duration of a unit test.

    Tests that legitimately exercise the engine builder re-patch
    `acme_core.db.engine.create_engine` with their own recorder, which
    overrides this because monkeypatch applies last-write-wins.
    """
    from acme_core.db import engine as engine_module

    def _forbidden(*_args: Any, **_kwargs: Any) -> NoReturn:
        raise AssertionError(
            "unit tests must not construct a database engine; "
            "move this test to tests/integration/ or patch create_engine"
        )

    monkeypatch.setattr(engine_module, "create_engine", _forbidden)
    engine_module.dispose_engine()
    yield
    engine_module.dispose_engine()
