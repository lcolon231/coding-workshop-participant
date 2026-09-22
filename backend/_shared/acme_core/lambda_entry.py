"""Decide what kind of Lambda invocation an event is, before acting on it.

Every service's `function.py` asks this module one question -- is this an
HTTP request, an administrative command, or neither? -- and only then imports
the web stack or the admin actions. Keeping the answer here, as a pure
function, puts the riskiest branch in the codebase inside the coverage source
instead of in an untested handler file.

The admin test is a *positive* assertion. The earlier draft treated "anything
that is not HTTP" as an admin command, which is safe for Function URL traffic
today but fails open the moment anything else can invoke the function: an SQS
trigger, an EventBridge rule or a DLQ redrive carries no `requestContext` and
would have been dispatched as `migrate`. Now an event is admin only when it
carries the marker, carries no HTTP key at all, names an allowlisted action and
has nothing else. Anything unrecognised -- including `{}`, `None` and the AWS
console's default test payload -- is rejected rather than handed to Mangum,
where it used to die with an opaque KeyError.
"""

from __future__ import annotations

import enum
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

# Versioned so a future payload shape can be introduced alongside this one
# rather than silently reinterpreted. tools/db.sh sends exactly this value.
ADMIN_SOURCE = "acme.admin.v1"

ADMIN_ACTIONS = frozenset({"migrate", "seed", "db-current"})

# The only top-level keys an admin event may carry. Anything else means the
# event came from somewhere other than tools/db.sh.
_ADMIN_KEYS = frozenset({"source", "action", "options"})

# Keys that appear in some HTTP event format Mangum understands: Function URL
# and API Gateway payload 2.0, API Gateway REST (1.0) and ALB. The presence of
# any one of them disqualifies an event from the admin branch, so a request
# can never be steered into it however its fields are arranged.
HTTP_KEYS = frozenset({
    "version",
    "routeKey",
    "rawPath",
    "rawQueryString",
    "cookies",
    "headers",
    "multiValueHeaders",
    "queryStringParameters",
    "multiValueQueryStringParameters",
    "pathParameters",
    "stageVariables",
    "requestContext",
    "body",
    "isBase64Encoded",
    "httpMethod",
    "path",
    "resource",
})


class Kind(enum.StrEnum):
    """What an invocation is."""

    HTTP = "http"
    ADMIN = "admin"
    REJECT = "reject"


@dataclass(frozen=True, slots=True)
class Decision:
    """The outcome of classifying one event.

    `reason` explains a rejection for the log line. It names which check
    failed, never the event's contents, which may carry a seed password.
    """

    kind: Kind
    action: str | None = None
    options: Mapping[str, Any] = field(default_factory=dict)
    reason: str | None = None

    @property
    def is_http(self) -> bool:
        """Whether the event should be handed to the ASGI adapter."""
        return self.kind is Kind.HTTP

    @property
    def is_admin(self) -> bool:
        """Whether the event is an allowlisted administrative command."""
        return self.kind is Kind.ADMIN


def _reject(reason: str) -> Decision:
    return Decision(kind=Kind.REJECT, reason=reason)


def _is_function_url_request(event: Mapping[str, Any]) -> bool:
    """Positively identify a Function URL (payload format 2.0) request.

    The Terraform only ever puts a Function URL in front of these functions,
    so that is the one HTTP shape accepted. It always carries
    `requestContext.http.method`; requiring it means a bare `{"headers": {}}`
    is not mistaken for traffic.
    """
    if event.get("version") != "2.0":
        return False
    context = event.get("requestContext")
    if not isinstance(context, Mapping):
        return False
    http = context.get("http")
    return isinstance(http, Mapping) and isinstance(http.get("method"), str)


def classify(event: object) -> Decision:
    """Classify a raw Lambda event. Never raises, never performs I/O.

    Args:
        event: Whatever the Lambda runtime delivered.

    Returns:
        An HTTP decision for a Function URL request, an admin decision for a
        well-formed `tools/db.sh` command, or a rejection naming the failed
        check. The caller must refuse a rejection outright.
    """
    if not isinstance(event, Mapping):
        return _reject("event is not an object")

    if event.get("source") != ADMIN_SOURCE:
        if _is_function_url_request(event):
            return Decision(kind=Kind.HTTP)
        return _reject("unrecognised event shape")

    # From here the event claims to be an admin command; every check must pass.
    if HTTP_KEYS.intersection(event):
        return _reject("admin marker on an event carrying HTTP keys")
    if not _ADMIN_KEYS.issuperset(event):
        return _reject("admin event carries unexpected keys")

    action = event.get("action")
    if not isinstance(action, str) or action not in ADMIN_ACTIONS:
        return _reject("admin action is not allowlisted")

    options = event.get("options", {})
    if options is None:
        options = {}
    if not isinstance(options, Mapping):
        return _reject("admin options is not an object")

    return Decision(kind=Kind.ADMIN, action=action, options=dict(options))
