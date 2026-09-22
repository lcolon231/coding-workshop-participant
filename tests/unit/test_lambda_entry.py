"""Lambda event classification: HTTP, admin, or refused -- and nothing fails open."""

from __future__ import annotations

import dataclasses
import re
from pathlib import Path
from typing import Any

import pytest

from acme_core.lambda_entry import (
    ADMIN_ACTIONS,
    ADMIN_SOURCE,
    HTTP_KEYS,
    Decision,
    Kind,
    classify,
)

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]

# Referenced by name so the tests can assert it never leaks into a reason.
FAKE_PW = "masked-value"


def function_url_event(**overrides: Any) -> dict[str, Any]:
    """A trimmed but structurally faithful Function URL payload 2.0 event."""
    event: dict[str, Any] = {
        "version": "2.0",
        "routeKey": "$default",
        "rawPath": "/api/auth/login",
        "rawQueryString": "",
        "headers": {"content-type": "application/json"},
        "requestContext": {
            "http": {"method": "POST", "path": "/api/auth/login", "protocol": "HTTP/1.1"},
            "requestId": "req-1",
        },
        "body": '{"email": "a@acme.inc"}',
        "isBase64Encoded": False,
    }
    event.update(overrides)
    return event


def admin_event(**overrides: Any) -> dict[str, Any]:
    """Exactly what tools/db.sh sends."""
    event: dict[str, Any] = {"source": ADMIN_SOURCE, "action": "migrate", "options": {}}
    event.update(overrides)
    return event


class TestHttp:
    def test_function_url_request(self) -> None:
        decision = classify(function_url_event())
        assert decision.is_http
        assert not decision.is_admin
        assert decision.action is None

    def test_a_body_naming_an_admin_action_is_still_http(self) -> None:
        """The body is a string; it never merges into the top-level event."""
        body = f'{{"source": "{ADMIN_SOURCE}", "action": "migrate"}}'
        assert classify(function_url_event(body=body)).is_http

    @pytest.mark.parametrize("version", [None, "1.0", 2.0, ""])
    def test_requires_payload_version_2(self, version: object) -> None:
        assert classify(function_url_event(version=version)).kind is Kind.REJECT

    def test_requires_a_request_context(self) -> None:
        event = function_url_event()
        del event["requestContext"]
        assert classify(event).kind is Kind.REJECT

    @pytest.mark.parametrize(
        "context",
        [None, "x", {}, {"http": None}, {"http": {}}, {"http": {"method": 1}}],
    )
    def test_requires_an_http_method(self, context: object) -> None:
        assert classify(function_url_event(requestContext=context)).kind is Kind.REJECT

    def test_headers_alone_are_not_a_request(self) -> None:
        assert classify({"headers": {}}).kind is Kind.REJECT


class TestAdmin:
    @pytest.mark.parametrize("action", sorted(ADMIN_ACTIONS))
    def test_each_allowlisted_action(self, action: str) -> None:
        decision = classify(admin_event(action=action))
        assert decision.is_admin
        assert not decision.is_http
        assert decision.action == action

    def test_options_are_passed_through(self) -> None:
        options = {"admin_password": FAKE_PW, "confirm": "app-123"}
        assert classify(admin_event(action="seed", options=options)).options == options

    def test_options_are_copied_not_shared(self) -> None:
        options: dict[str, Any] = {"confirm": "app-123"}
        decision = classify(admin_event(options=options))
        options["confirm"] = "changed"
        assert decision.options == {"confirm": "app-123"}

    def test_absent_options_become_empty(self) -> None:
        event = admin_event()
        del event["options"]
        assert classify(event).options == {}

    def test_null_options_become_empty(self) -> None:
        assert classify(admin_event(options=None)).options == {}


class TestFailClosed:
    """Every shape that is neither a Function URL request nor a db.sh command."""

    @pytest.mark.parametrize("event", [None, [], "migrate", 42, b"{}", ()])
    def test_non_objects(self, event: object) -> None:
        decision = classify(event)
        assert decision.kind is Kind.REJECT
        assert decision.reason == "event is not an object"

    @pytest.mark.parametrize(
        "event",
        [
            pytest.param({}, id="empty"),
            pytest.param(
                {"key1": "value1", "key2": "value2", "key3": "value3"},
                id="aws-console-default-test-event",
            ),
            pytest.param(
                {"Records": [{"eventSource": "aws:sqs", "body": "{}"}]},
                id="sqs",
            ),
            pytest.param(
                {"source": "aws.events", "detail-type": "Scheduled Event", "detail": {}},
                id="eventbridge",
            ),
        ],
    )
    def test_other_invocation_sources(self, event: dict[str, Any]) -> None:
        assert classify(event).kind is Kind.REJECT

    def test_an_action_without_the_marker(self) -> None:
        """The regression S11 fixed: the old negative test dispatched this."""
        assert classify({"action": "migrate", "options": {}}).kind is Kind.REJECT

    @pytest.mark.parametrize("source", ["acme.admin.v2", "ACME.ADMIN.V1", "acme.admin", "", None])
    def test_the_marker_must_match_exactly(self, source: object) -> None:
        assert classify(admin_event(source=source)).kind is Kind.REJECT

    @pytest.mark.parametrize("key", sorted(HTTP_KEYS))
    def test_the_marker_on_an_http_shaped_event(self, key: str) -> None:
        decision = classify(admin_event(**{key: "x"}))
        assert decision.kind is Kind.REJECT
        assert decision.reason == "admin marker on an event carrying HTTP keys"

    def test_the_marker_on_a_real_function_url_event(self) -> None:
        assert classify(function_url_event(source=ADMIN_SOURCE)).kind is Kind.REJECT

    def test_the_marker_inside_an_eventbridge_envelope(self) -> None:
        event = admin_event(**{"detail-type": "x", "detail": {}})
        decision = classify(event)
        assert decision.kind is Kind.REJECT
        assert decision.reason == "admin event carries unexpected keys"

    @pytest.mark.parametrize(
        "action", ["drop", "", None, 1, "MIGRATE", " migrate", "migrate ", ["migrate"]]
    )
    def test_actions_outside_the_allowlist(self, action: object) -> None:
        decision = classify(admin_event(action=action))
        assert decision.kind is Kind.REJECT
        assert decision.reason == "admin action is not allowlisted"

    def test_a_missing_action(self) -> None:
        event = admin_event()
        del event["action"]
        assert classify(event).kind is Kind.REJECT

    @pytest.mark.parametrize("options", [[], "x", 1, True])
    def test_options_that_are_not_an_object(self, options: object) -> None:
        decision = classify(admin_event(options=options))
        assert decision.kind is Kind.REJECT
        assert decision.reason == "admin options is not an object"


class TestDecision:
    def test_a_rejection_never_echoes_the_event(self) -> None:
        """Reasons are logged; a seed payload carries a password."""
        events = [
            admin_event(action=FAKE_PW, options={"admin_password": FAKE_PW}),
            admin_event(options=FAKE_PW),
            admin_event(extra=FAKE_PW),
            admin_event(body=FAKE_PW),
            {"admin_password": FAKE_PW},
        ]
        for event in events:
            decision = classify(event)
            assert decision.kind is Kind.REJECT
            assert FAKE_PW not in (decision.reason or "")

    def test_every_rejection_has_a_reason(self) -> None:
        for event in (None, {}, admin_event(action="drop"), function_url_event(version="1.0")):
            assert classify(event).reason

    def test_accepted_decisions_carry_no_reason(self) -> None:
        assert classify(function_url_event()).reason is None
        assert classify(admin_event()).reason is None

    def test_is_immutable(self) -> None:
        decision = classify(admin_event())
        with pytest.raises(dataclasses.FrozenInstanceError):
            decision.action = "seed"  # type: ignore[misc]

    def test_default_options_are_not_shared(self) -> None:
        assert Decision(kind=Kind.HTTP).options is not Decision(kind=Kind.HTTP).options


class TestDrift:
    def test_allowlist_matches_tools_db_sh(self) -> None:
        """The CLI and the dispatcher must agree on what can be invoked."""
        script = (REPO_ROOT / "tools" / "db.sh").read_text()
        match = re.search(r"^\s*([a-z|-]+)\)\s*;;", script, re.MULTILINE)
        assert match is not None
        assert frozenset(match.group(1).split("|")) == ADMIN_ACTIONS

    def test_marker_matches_tools_db_sh(self) -> None:
        script = (REPO_ROOT / "tools" / "db.sh").read_text()
        assert f'\\"source\\":\\"{ADMIN_SOURCE}\\"' in script
