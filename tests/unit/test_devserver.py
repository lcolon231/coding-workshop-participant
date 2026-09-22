"""The local dev server: one process, every service, dispatched by prefix."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tools import devserver

pytestmark = pytest.mark.unit


class TestDiscovery:
    def test_finds_every_deployable_service(self) -> None:
        found = devserver.discover_services()
        assert "auth" in found and "incidents" in found
        assert not any(name.startswith("_") for name in found)


class TestCombined:
    @pytest.fixture
    def client(self, monkeypatch: pytest.MonkeyPatch) -> TestClient:
        monkeypatch.delenv("ACME_SERVICE_NAME", raising=False)
        return TestClient(devserver.app(), raise_server_exceptions=False)

    @pytest.mark.parametrize("service", ["auth", "incidents"])
    def test_each_prefix_reaches_its_own_service(self, client: TestClient, service: str) -> None:
        """/healthz builds no engine, so this runs under the unit tier's no-I/O guard."""
        resp = client.get(f"/api/{service}/healthz")
        assert resp.status_code == 200
        assert resp.json()["service"] == service

    @pytest.mark.parametrize("service", ["auth", "incidents"])
    def test_each_service_keeps_its_own_docs(self, client: TestClient, service: str) -> None:
        schema = client.get(f"/api/{service}/openapi.json").json()
        assert all(path.startswith(f"/api/{service}/") for path in schema["paths"])

    def test_a_service_404_is_the_service_envelope(self, client: TestClient) -> None:
        resp = client.get("/api/auth/nope")
        assert resp.status_code == 404
        assert resp.json()["error"] == "not_found"
        assert resp.headers["x-request-id"]

    @pytest.mark.parametrize("path", ["/", "/api", "/api/nope/healthz", "/api/authz/healthz"])
    def test_an_unmounted_prefix_gets_the_same_envelope(
        self, client: TestClient, path: str
    ) -> None:
        """`/api/authz` must not be mistaken for `/api/auth`."""
        resp = client.get(path)
        assert resp.status_code == 404
        assert set(resp.json()) == {"error", "message", "details", "request_id"}
        assert resp.json()["error"] == "not_found"


class TestSingle:
    def test_naming_a_service_serves_only_that_one(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ACME_SERVICE_NAME", "incidents")
        client = TestClient(devserver.app(), raise_server_exceptions=False)
        assert client.get("/api/incidents/healthz").json()["service"] == "incidents"
        assert client.get("/api/auth/healthz").status_code == 404

    def test_a_service_without_a_package_gets_the_shared_routes(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ACME_SERVICE_NAME", "facilities")
        client = TestClient(devserver.app(), raise_server_exceptions=False)
        assert client.get("/api/facilities/healthz").json()["service"] == "facilities"
