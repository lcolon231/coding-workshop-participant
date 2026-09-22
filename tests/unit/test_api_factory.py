"""The shared application factory: routing, probes, docs and middleware."""

from __future__ import annotations

import pytest
from fastapi import APIRouter
from fastapi.testclient import TestClient

from acme_core.api import create_app, reset_readiness_cache
from acme_core.db import engine as engine_module

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _clear_readiness() -> None:
    reset_readiness_cache()


@pytest.fixture
def client() -> TestClient:
    router = APIRouter()

    @router.get("/widgets")
    def _widgets() -> list[str]:
        return []

    return TestClient(
        create_app("auth", [router], configure_logs=False),
        raise_server_exceptions=False,
    )


class TestRoutingPrefix:
    def test_routes_mount_under_the_service_prefix(self, client: TestClient) -> None:
        """CloudFront routes only /api/<name>*; an unprefixed route is unreachable."""
        assert client.get("/api/auth/widgets").status_code == 200

    def test_unprefixed_path_is_not_served(self, client: TestClient) -> None:
        assert client.get("/widgets").status_code == 404

    def test_prefix_follows_the_service_name(self) -> None:
        app = create_app("incidents", configure_logs=False)
        assert TestClient(app).get("/api/incidents/healthz").status_code == 200


class TestDocumentation:
    def test_docs_are_under_the_prefix(self, client: TestClient) -> None:
        """At the root these are unreachable through CloudFront."""
        assert client.get("/api/auth/docs").status_code == 200

    def test_openapi_is_under_the_prefix(self, client: TestClient) -> None:
        assert client.get("/api/auth/openapi.json").status_code == 200

    def test_root_docs_are_not_served(self, client: TestClient) -> None:
        assert client.get("/docs").status_code == 404

    def test_schema_documents_400_not_422(self, client: TestClient) -> None:
        """Our handler returns 400; FastAPI would otherwise publish its own 422."""
        schema = client.get("/api/auth/openapi.json").json()
        codes = {
            code
            for methods in schema["paths"].values()
            for op in methods.values()
            for code in op.get("responses", {})
        }
        assert "422" not in codes


class TestLiveness:
    def test_healthz_is_ok(self, client: TestClient) -> None:
        assert client.get("/api/auth/healthz").json()["status"] == "ok"

    def test_healthz_builds_no_engine(self, client: TestClient) -> None:
        """A liveness probe that touches a scale-to-zero Aurora would flap.

        The unit-tier guard makes engine construction raise, so a 200 here is
        itself proof that no engine was built.
        """
        client.get("/api/auth/healthz")
        assert engine_module._engine is None

    def test_healthz_reports_build_provenance(self, client: TestClient) -> None:
        """Turns "is the deployed code current?" into one curl."""
        assert "git_sha" in client.get("/api/auth/healthz").json()["build"]

    def test_healthz_names_the_service(self, client: TestClient) -> None:
        assert client.get("/api/auth/healthz").json()["service"] == "auth"


class TestReadiness:
    def test_unreachable_database_is_503(self, client: TestClient) -> None:
        """The guard fixture makes the engine raise, standing in for an outage."""
        resp = client.get("/api/auth/readyz")
        assert resp.status_code == 503
        assert resp.json()["database"] is False

    def test_reachable_database_is_200(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("acme_core.api._check_database", lambda: True)
        reset_readiness_cache()
        assert client.get("/api/auth/readyz").status_code == 200

    def test_success_is_cached(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Unauthenticated and public: uncached it is a cost-amplification lever."""
        calls = {"n": 0}

        def _counted() -> bool:
            calls["n"] += 1
            return True

        monkeypatch.setattr("acme_core.api._check_database", _counted)
        reset_readiness_cache()
        for _ in range(5):
            client.get("/api/auth/readyz")
        assert calls["n"] == 1

    def test_failure_is_not_cached(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Recovery must be noticed promptly; only success is worth caching."""
        calls = {"n": 0}

        def _counted() -> bool:
            calls["n"] += 1
            return False

        monkeypatch.setattr("acme_core.api._check_database", _counted)
        reset_readiness_cache()
        client.get("/api/auth/readyz")
        client.get("/api/auth/readyz")
        assert calls["n"] == 2

    def test_does_not_expose_the_migration_revision(self, client: TestClient) -> None:
        """A revision maps to a public commit, advertising known issues."""
        body = client.get("/api/auth/readyz").json()
        assert not any("revision" in k or "sha" in k for k in body)


class TestRequestCorrelation:
    def test_response_carries_the_header(self, client: TestClient) -> None:
        assert client.get("/api/auth/healthz").headers["X-Request-Id"]

    def test_each_request_gets_a_fresh_id(self, client: TestClient) -> None:
        """Isolation comes from setting a new id per request, not from clearing."""
        first = client.get("/api/auth/healthz").headers["X-Request-Id"]
        second = client.get("/api/auth/healthz").headers["X-Request-Id"]
        assert first != second


class TestCors:
    def test_no_cors_middleware_is_installed(self, client: TestClient) -> None:
        """infra/lambda.tf:44-51 already sets CORS at the Function URL layer.

        A second Access-Control-Allow-Origin makes browsers reject the response
        outright, and both environments are same-origin anyway.
        """
        resp = client.get("/api/auth/healthz", headers={"Origin": "https://evil.example"})
        assert "access-control-allow-origin" not in resp.headers
