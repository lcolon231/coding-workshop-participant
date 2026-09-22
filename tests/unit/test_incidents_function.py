"""The incidents Lambda handler: classify, then serve HTTP -- or refuse.

`backend/auth/function.py` and `backend/incidents/function.py` are both
called `function`, and pythonpath resolves the bare name to the auth one, so
this module loads the incidents handler by path.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from acme_core import admin_actions

pytestmark = pytest.mark.unit

_FUNCTION_PY = Path(__file__).resolve().parents[2] / "backend" / "incidents" / "function.py"


def function_url_event(path: str = "/api/incidents/healthz", method: str = "GET") -> dict[str, Any]:
    """A Function URL payload 2.0 event, as the Lambda runtime delivers it."""
    return {
        "version": "2.0",
        "routeKey": "$default",
        "rawPath": path,
        "rawQueryString": "",
        "headers": {"host": "abc.lambda-url.us-east-2.on.aws", "accept": "application/json"},
        "requestContext": {
            "accountId": "anonymous",
            "apiId": "abc",
            "domainName": "abc.lambda-url.us-east-2.on.aws",
            "domainPrefix": "abc",
            "http": {
                "method": method,
                "path": path,
                "protocol": "HTTP/1.1",
                "sourceIp": "203.0.113.7",
                "userAgent": "pytest",
            },
            "requestId": "req-1",
            "routeKey": "$default",
            "stage": "$default",
            "time": "22/Sep/2026:12:00:00 +0000",
            "timeEpoch": 1790078400000,
        },
        "isBase64Encoded": False,
    }


@pytest.fixture
def function() -> Iterator[ModuleType]:
    """The incidents handler module, freshly loaded so `_asgi` starts empty."""
    spec = importlib.util.spec_from_file_location("incidents_function", _FUNCTION_PY)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
        yield module
    finally:
        sys.modules.pop(spec.name, None)


class TestHttp:
    def test_serves_a_function_url_request(self, function: ModuleType) -> None:
        """/healthz builds no engine, so this runs under the unit tier's no-I/O guard."""
        response = function.handler(function_url_event(), None)
        assert response["statusCode"] == 200
        assert json.loads(response["body"])["service"] == "incidents"

    def test_docs_live_under_the_service_prefix(self, function: ModuleType) -> None:
        response = function.handler(function_url_event("/api/incidents/openapi.json"), None)
        assert response["statusCode"] == 200
        schema = json.loads(response["body"])
        assert schema["info"]["title"].endswith("incidents")
        assert all(
            p == "/api/incidents" or p.startswith("/api/incidents/") for p in schema["paths"]
        )

    def test_builds_the_adapter_once_and_reuses_it(self, function: ModuleType) -> None:
        function.handler(function_url_event(), None)
        adapter = function._asgi
        function.handler(function_url_event(), None)
        assert adapter is not None and function._asgi is adapter


class TestRefusal:
    def test_an_admin_command_is_refused_by_name(
        self, function: ModuleType, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Only the auth function migrates or seeds; this one must not even try."""

        def _never(*_: Any) -> None:
            raise AssertionError("the incidents handler dispatched an admin action")

        monkeypatch.setattr(admin_actions, "run_admin_action", _never)
        event = {"source": "acme.admin.v1", "action": "migrate"}
        with pytest.raises(RuntimeError, match="served by the auth function"):
            function.handler(event, None)
        assert function._asgi is None

    @pytest.mark.parametrize(
        "event",
        [
            pytest.param(None, id="none"),
            pytest.param({}, id="empty"),
            pytest.param({"key1": "value1"}, id="console-test-event"),
            pytest.param({"action": "migrate"}, id="action-without-marker"),
        ],
    )
    def test_anything_else_fails_loudly(self, function: ModuleType, event: object) -> None:
        with pytest.raises(RuntimeError, match="unrecognised invocation"):
            function.handler(event, None)

    def test_the_error_never_echoes_the_event(self, function: ModuleType) -> None:
        event = {"source": "acme.admin.v1", "action": "seed", "admin_password": "masked-value-1"}
        with pytest.raises(RuntimeError) as exc:
            function.handler(event, None)
        assert "masked-value-1" not in str(exc.value)
