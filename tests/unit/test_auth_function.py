"""The auth Lambda handler: classify, then dispatch -- or refuse."""

from __future__ import annotations

import json
from typing import Any

import pytest

import function
from acme_core import admin_actions

pytestmark = pytest.mark.unit


def function_url_event(path: str = "/api/auth/healthz", method: str = "GET") -> dict[str, Any]:
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


@pytest.fixture(autouse=True)
def _fresh_adapter(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(function, "_asgi", None)


class TestHttp:
    def test_serves_a_function_url_request(self) -> None:
        """/healthz builds no engine, so this runs under the unit tier's no-I/O guard."""
        response = function.handler(function_url_event(), None)
        assert response["statusCode"] == 200
        assert json.loads(response["body"])["service"] == "auth"

    def test_builds_the_adapter_once_and_reuses_it(self) -> None:
        function.handler(function_url_event(), None)
        adapter = function._asgi
        function.handler(function_url_event(), None)
        assert adapter is not None and function._asgi is adapter


class TestAdmin:
    def test_dispatches_an_admin_command(self, monkeypatch: pytest.MonkeyPatch) -> None:
        seen: list[tuple[str, dict[str, Any]]] = []
        monkeypatch.setattr(
            admin_actions, "run_admin_action",
            lambda action, options: seen.append((action, dict(options))) or {"ok": True},
        )
        event = {"source": "acme.admin.v1", "action": "db-current", "options": {"x": 1}}
        assert function.handler(event, None) == {"ok": True}
        assert seen == [("db-current", {"x": 1})]

    def test_an_admin_command_never_builds_the_adapter(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The web stack is imported at module scope now (init-phase CPU), but
        an admin invocation still constructs no ASGI adapter."""
        monkeypatch.setattr(admin_actions, "run_admin_action", lambda *_: {"ok": True})
        function.handler({"source": "acme.admin.v1", "action": "migrate"}, None)
        assert function._asgi is None


class TestRefusal:
    @pytest.mark.parametrize(
        "event",
        [
            pytest.param(None, id="none"),
            pytest.param({}, id="empty"),
            pytest.param({"key1": "value1"}, id="console-test-event"),
            pytest.param({"action": "migrate"}, id="action-without-marker"),
        ],
    )
    def test_anything_else_fails_loudly(self, event: object) -> None:
        with pytest.raises(RuntimeError, match="unrecognised invocation"):
            function.handler(event, None)

    def test_the_error_never_echoes_the_event(self) -> None:
        event = {"source": "acme.admin.v1", "action": "seed", "admin_password": "masked-value-1"}
        with pytest.raises(RuntimeError) as exc:
            function.handler(event, None)
        assert "masked-value-1" not in str(exc.value)
