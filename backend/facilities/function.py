"""AWS Lambda entrypoint for the facilities service.

`infra/locals.tf:57` hardcodes the handler as `function.handler`, so both this
module's name and the function's name are load-bearing.

Every event is classified before anything heavy is imported. An HTTP request
builds the ASGI stack on first use and reuses it while the environment stays
warm (A2). Administrative commands are refused here, not dispatched: migrate
and seed ship only with the auth function (tools/sync-shared.sh AUTH_ONLY), so
a schema change has one door rather than three. Anything else is refused
rather than handed to Mangum (S11).
"""

from __future__ import annotations

from typing import Any

from acme_core.lambda_entry import classify
from acme_core.logging_config import get_logger

_logger = get_logger(__name__)

_ADMIN_REFUSED = "admin commands are served by the auth function only"

# Built on the first HTTP event, not at import: see the module docstring.
_asgi: Any = None


def handler(event: Any = None, context: Any = None) -> Any:
    """Dispatch one Lambda invocation.

    Args:
        event: Whatever the Lambda runtime delivered.
        context: The Lambda context object.

    Returns:
        A Function URL response.

    Raises:
        RuntimeError: The event is not a Function URL request. An admin
            command is refused by name so the operator learns which function
            to invoke instead; anything else fails loudly rather than
            silently succeeding.
    """
    decision = classify(event)

    if not decision.is_http:
        # The reason names the failed check, never the event, which for a
        # malformed seed command could carry a password.
        reason = _ADMIN_REFUSED if decision.is_admin else decision.reason
        _logger.error("unrecognised_invocation", extra={"reason": reason})
        raise RuntimeError(f"unrecognised invocation: {reason}")

    global _asgi
    if _asgi is None:
        from mangum import Mangum

        from facilities_service.app import app

        _asgi = Mangum(app, lifespan="off")
    return _asgi(event, context)
