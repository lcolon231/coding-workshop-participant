"""Structured logging: JSON shape, correlation, and what must never appear."""

from __future__ import annotations

import json
import logging

import pytest

from acme_core.logging_config import (
    JsonFormatter,
    configure_logging,
    get_request_id,
    is_secret_key,
    new_request_id,
    redact,
    set_request_id,
)

pytestmark = pytest.mark.unit

# Obvious placeholder, referenced by name so no file pairs a literal with a
# host/user/port and trips secret scanners (GitGuardian). Not a credential.
FAKE_PW = "masked-value"


def _render(msg: str = "hello", **extra: object) -> dict[str, object]:
    """Format one record through the real formatter and parse it back."""
    record = logging.LogRecord("acme.test", logging.INFO, __file__, 1, msg, None, None)
    for key, value in extra.items():
        setattr(record, key, value)
    return json.loads(JsonFormatter().format(record))


class TestJsonShape:
    def test_emits_valid_json(self) -> None:
        assert _render()["message"] == "hello"

    def test_carries_level_and_logger(self) -> None:
        line = _render()
        assert line["level"] == "INFO"
        assert line["logger"] == "acme.test"

    def test_extras_are_included(self) -> None:
        assert _render(incident_id="abc-123")["incident_id"] == "abc-123"

    def test_unserialisable_extras_do_not_raise(self) -> None:
        """A UUID or datetime in `extra` must never break logging itself."""
        assert _render(when=object())["when"]

    def test_exception_is_rendered(self) -> None:
        try:
            raise ValueError("boom")
        except ValueError:
            record = logging.LogRecord(
                "acme.test", logging.ERROR, __file__, 1, "failed", None, None
            )
            import sys

            record.exc_info = sys.exc_info()
            line = json.loads(JsonFormatter().format(record))
        assert "ValueError: boom" in line["exception"]


class TestRedaction:
    @pytest.mark.parametrize(
        "key",
        ["password", "PASSWORD", "passwd", "refresh_token", "access_token",
         "Authorization", "jwt_secret", "POSTGRES_PASS", "api_key"],
    )
    def test_credential_keys_are_detected(self, key: str) -> None:
        assert is_secret_key(key) is True

    @pytest.mark.parametrize("key", ["email", "incident_id", "building", "status"])
    def test_ordinary_keys_are_not(self, key: str) -> None:
        assert is_secret_key(key) is False

    def test_top_level_value_is_replaced(self) -> None:
        assert redact({"password": FAKE_PW})["password"] == "***"

    def test_nested_value_is_replaced(self) -> None:
        out = redact({"body": {"user": {"refresh_token": "xyz"}}})
        assert out["body"]["user"]["refresh_token"] == "***"

    def test_inside_a_list(self) -> None:
        out = redact({"items": [{"password": "a"}, {"password": "b"}]})
        assert [i["password"] for i in out["items"]] == ["***", "***"]

    def test_non_secret_values_survive(self) -> None:
        assert redact({"email": "a@acme.inc"})["email"] == "a@acme.inc"

    def test_secret_extra_never_reaches_output(self) -> None:
        """The property that matters: a credential cannot reach CloudWatch."""
        assert FAKE_PW not in json.dumps(_render(password=FAKE_PW))

    def test_secret_nested_in_an_extra_never_reaches_output(self) -> None:
        line = _render(request_body={"email": "a@acme.inc", "password": FAKE_PW})
        assert FAKE_PW not in json.dumps(line)


class TestRequestCorrelation:
    def test_absent_by_default(self) -> None:
        set_request_id(None)
        assert get_request_id() is None

    def test_round_trip(self) -> None:
        set_request_id("abc")
        assert get_request_id() == "abc"
        set_request_id(None)

    def test_included_in_every_line(self) -> None:
        set_request_id("req-42")
        try:
            assert _render()["request_id"] == "req-42"
        finally:
            set_request_id(None)

    def test_prefers_the_lambda_request_id(self) -> None:
        """Lets a log line be matched against the platform's own REPORT record."""

        class _Ctx:
            aws_request_id = "lambda-abc"

        assert new_request_id(_Ctx()) == "lambda-abc"

    def test_falls_back_to_a_uuid(self) -> None:
        first, second = new_request_id(None), new_request_id(None)
        assert first != second and len(first) == 36

    def test_handles_a_context_without_the_attribute(self) -> None:
        assert new_request_id(object())


class TestConfigureLogging:
    def test_replaces_existing_handlers(self) -> None:
        """The Lambda runtime installs its own; two handlers means double logs."""
        root = logging.getLogger()
        root.addHandler(logging.StreamHandler())
        configure_logging()
        assert len(root.handlers) == 1
        assert isinstance(root.handlers[0].formatter, JsonFormatter)


class TestOverMatching:
    """Redaction errs toward over-matching; record which way and why."""

    def test_the_injected_platform_variable_is_caught(self) -> None:
        """infra/locals.tf:108 injects POSTGRES_PASS, not POSTGRES_PASSWORD."""
        assert is_secret_key("POSTGRES_PASS") is True

    def test_over_matching_is_accepted(self) -> None:
        """Documents the trade-off rather than leaving it to be rediscovered."""
        assert is_secret_key("passed_checks") is True
