"""Readiness reporting against a real, migrated database."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from acme_core.api import create_app, reset_readiness_cache
from acme_core.db.migrate import downgrade, upgrade_head

pytestmark = pytest.mark.integration


@pytest.fixture
def client() -> TestClient:
    reset_readiness_cache()
    return TestClient(create_app("auth", configure_logs=False), raise_server_exceptions=False)


class TestReadyz:
    def test_migrated_database_is_ready(self, client: TestClient) -> None:
        body = client.get("/api/auth/readyz").json()
        assert body["status"] == "ready"
        assert body["database"] is True
        assert body["migrations_pending"] is False

    def test_pending_migrations_report_503(
        self, client: TestClient, database_url: str
    ) -> None:
        """A forgotten migrate-cloud should be loud, not a later UndefinedTable."""
        try:
            downgrade("base", database_url)
            reset_readiness_cache()
            resp = client.get("/api/auth/readyz")
            assert resp.status_code == 503
            assert resp.json()["migrations_pending"] is True
        finally:
            upgrade_head(database_url)
            reset_readiness_cache()

    def test_recovers_once_migrated(self, client: TestClient) -> None:
        assert client.get("/api/auth/readyz").status_code == 200

    def test_never_exposes_the_revision(self, client: TestClient) -> None:
        """A revision id maps to a public commit."""
        body = client.get("/api/auth/readyz").json()
        assert not any("revision" in key or "sha" in key for key in body)
        # Booleans, a status string, or null when a check could not run.
        assert all(v is None or isinstance(v, (bool, str)) for v in body.values())
