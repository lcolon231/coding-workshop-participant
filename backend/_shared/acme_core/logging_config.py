"""Structured logging with request correlation and secret redaction.

Logs go to stdout as one JSON object per line, which is what CloudWatch Logs
Insights can query directly. Every line carries the request id, so "it broke"
becomes a single query rather than a guess.
"""

from __future__ import annotations

import json
import logging
import sys
import uuid
from contextvars import ContextVar
from typing import Any

# Per-request, and safe under both the Lambda single-invocation model and the
# threadpool uvicorn runs sync endpoints in.
_request_id: ContextVar[str | None] = ContextVar("acme_request_id", default=None)

# Substrings that mark a field as unloggable, matched case-insensitively against
# the key. "pass" rather than "password" on purpose: it also catches POSTGRES_PASS,
# which is the variable the platform actually injects (infra/locals.tf:108).
# Over-matching here is the safe direction -- a redacted "passed_checks" is a
# cosmetic annoyance, a logged credential is permanent in CloudWatch.
_SECRET_MARKERS = (
    "pass",
    "secret",
    "token",
    "authorization",
    "api_key",
    "credential",
)

_REDACTED = "***"

# LogRecord's own attributes; anything else on a record is caller-supplied extra.
_STANDARD_FIELDS = frozenset(vars(logging.LogRecord("", 0, "", 0, "", None, None)))


def is_secret_key(key: str) -> bool:
    """Return True when a field name suggests a credential.

    Args:
        key: The field name.

    Returns:
        True when the value must be redacted.
    """
    lowered = key.lower()
    return any(marker in lowered for marker in _SECRET_MARKERS)


def redact(value: Any) -> Any:
    """Recursively replace credential-looking values.

    Args:
        value: Any loggable structure.

    Returns:
        The same structure with secret values replaced.
    """
    if isinstance(value, dict):
        return {
            k: (_REDACTED if is_secret_key(str(k)) else redact(v)) for k, v in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [redact(v) for v in value]
    return value


class JsonFormatter(logging.Formatter):
    """Render a record as a single JSON line."""

    def format(self, record: logging.LogRecord) -> str:
        """Serialise the record, redacting anything credential-shaped.

        Args:
            record: The record to render.

        Returns:
            A JSON string.
        """
        payload: dict[str, Any] = {
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": get_request_id(),
        }
        for key, value in vars(record).items():
            if key in _STANDARD_FIELDS or key.startswith("_"):
                continue
            payload[key] = _REDACTED if is_secret_key(key) else redact(value)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        # default=str so a UUID or datetime in `extra` cannot make logging raise.
        return json.dumps(payload, default=str)


def get_request_id() -> str | None:
    """Return the current request's correlation id.

    Returns:
        The id, or None outside a request.
    """
    return _request_id.get()


def set_request_id(value: str | None) -> None:
    """Set the correlation id for the current context.

    Args:
        value: The id, or None to clear it.
    """
    _request_id.set(value)


def new_request_id(aws_context: Any = None) -> str:
    """Derive an id for one request.

    Prefers Lambda's own request id so a log line can be matched against the
    platform's REPORT record; falls back to a uuid4 under uvicorn.

    Args:
        aws_context: The Lambda context object, when present.

    Returns:
        The correlation id.
    """
    aws_id = getattr(aws_context, "aws_request_id", None)
    return str(aws_id) if aws_id else str(uuid.uuid4())


def configure_logging(level: int = logging.INFO) -> None:
    """Install the JSON formatter on the root logger.

    Replaces existing handlers: the Lambda runtime installs its own, which
    would otherwise emit a second, unstructured copy of every line.

    Args:
        level: Minimum level to emit.
    """
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)


def get_logger(name: str) -> logging.Logger:
    """Return a module logger.

    Args:
        name: Usually `__name__`.

    Returns:
        The logger.
    """
    return logging.getLogger(name)
