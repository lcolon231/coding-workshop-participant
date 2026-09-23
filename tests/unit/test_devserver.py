"""The local dev server: one process, every service, dispatched by prefix."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import create_model

from tools import devserver

pytestmark = pytest.mark.unit


class TestDiscovery:
    def test_finds_every_deployable_service(self) -> None:
        found = devserver.discover_services()
        assert {"auth", "incidents", "facilities"} <= set(found)
        assert not any(name.startswith("_") for name in found)


class TestCombined:
    @pytest.fixture
    def client(self, monkeypatch: pytest.MonkeyPatch) -> TestClient:
        monkeypatch.delenv("ACME_SERVICE_NAME", raising=False)
        return TestClient(devserver.app(), raise_server_exceptions=False)

    @pytest.mark.parametrize("service", ["auth", "incidents", "facilities"])
    def test_each_prefix_reaches_its_own_service(self, client: TestClient, service: str) -> None:
        """/healthz builds no engine, so this runs under the unit tier's no-I/O guard."""
        resp = client.get(f"/api/{service}/healthz")
        assert resp.status_code == 200
        assert resp.json()["service"] == service

    @pytest.mark.parametrize("service", ["auth", "incidents", "facilities"])
    def test_each_service_keeps_its_own_docs(self, client: TestClient, service: str) -> None:
        schema = client.get(f"/api/{service}/openapi.json").json()
        prefix = f"/api/{service}"
        assert all(p == prefix or p.startswith(f"{prefix}/") for p in schema["paths"])

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


class TestCombinedDocs:
    @pytest.fixture
    def client(self, monkeypatch: pytest.MonkeyPatch) -> TestClient:
        monkeypatch.delenv("ACME_SERVICE_NAME", raising=False)
        return TestClient(devserver.app(), raise_server_exceptions=False)

    def test_one_page_over_every_service(self, client: TestClient) -> None:
        page = client.get("/api/docs")
        assert page.status_code == 200
        assert page.headers["content-type"].startswith("text/html")
        assert "/api/openapi.json" in page.text

    def test_the_schema_holds_every_service_and_groups_by_it(self, client: TestClient) -> None:
        schema = client.get("/api/openapi.json").json()
        assert "/api/auth/login" in schema["paths"]
        assert "/api/incidents/healthz" in schema["paths"]
        for path, operations in schema["paths"].items():
            service = path.split("/")[2]
            for operation in operations.values():
                assert all(tag.startswith(f"{service}: ") for tag in operation["tags"])
        assert "HTTPBearer" in schema["components"]["securitySchemes"]
        # Shared by every service, identical, so kept once under its own name.
        assert "HealthResponse" in schema["components"]["schemas"]
        assert "IncidentsHealthResponse" not in schema["components"]["schemas"]

    def test_a_conflicting_schema_name_is_renamed_not_overwritten(self) -> None:
        first, second = FastAPI(), FastAPI()
        one = create_model("Thing", a=(int, ...))
        two = create_model("Thing", b=(str, ...))

        @first.get("/api/one/thing", response_model=one)
        def _one() -> None: ...

        @second.get("/api/two/thing", response_model=two)
        def _two() -> None: ...

        merged = devserver.merge_openapi({"one": first, "two": second})
        schemas = merged["components"]["schemas"]
        assert "a" in schemas["Thing"]["properties"]
        assert "b" in schemas["TwoThing"]["properties"]
        ref = merged["paths"]["/api/two/thing"]["get"]["responses"]["200"]["content"]
        assert ref["application/json"]["schema"]["$ref"] == "#/components/schemas/TwoThing"


class TestSingle:
    def test_naming_a_service_serves_only_that_one(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ACME_SERVICE_NAME", "incidents")
        client = TestClient(devserver.app(), raise_server_exceptions=False)
        assert client.get("/api/incidents/healthz").json()["service"] == "incidents"
        assert client.get("/api/auth/healthz").status_code == 404
        # The combined page belongs to the dispatcher, not to any one service.
        assert client.get("/api/docs").status_code == 404

    def test_a_service_without_a_package_gets_the_shared_routes(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ACME_SERVICE_NAME", "widgets")
        client = TestClient(devserver.app(), raise_server_exceptions=False)
        assert client.get("/api/widgets/healthz").json()["service"] == "widgets"
