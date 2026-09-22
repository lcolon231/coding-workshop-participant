"""AWS Lambda entrypoint for the auth service.

`infra/locals.tf:57` hardcodes the handler as `function.handler`, so both this
module's name and the function's name are load-bearing.

Every event is classified before anything heavy is imported. An HTTP request
builds the ASGI stack on first use and reuses it while the environment stays
warm; an admin command imports only what it runs, so `migrate` never loads
FastAPI and the route graph alongside Alembic inside a 128 MB function (A2).
Anything else is refused rather than handed to Mangum (S11).
"""

from __future__ import annotations

from typing import Any

from acme_core.lambda_entry import classify
from acme_core.logging_config import get_logger

_logger = get_logger(__name__)

# Built on the first HTTP event, not at import: see the module docstring.
_asgi: Any = None


def handler(event: Any = None, context: Any = None) -> Any:
    """Dispatch one Lambda invocation.

    Args:
        event: Whatever the Lambda runtime delivered.
        context: The Lambda context object.

    Returns:
        A Function URL response for HTTP events, or the admin action's result.

    Raises:
        RuntimeError: The event is neither a Function URL request nor a
            well-formed admin command. Failing loudly is the point: a silent
            success on an unrecognised event is how a fail-open bug hides.
    """
    decision = classify(event)

    if decision.is_admin and decision.action is not None:
        from acme_core.admin_actions import run_admin_action

        return run_admin_action(decision.action, decision.options)

    if not decision.is_http:
        # The reason names the failed check, never the event, which for a
        # malformed seed command could carry a password.
        _logger.error("unrecognised_invocation", extra={"reason": decision.reason})
        raise RuntimeError(f"unrecognised invocation: {decision.reason}")

    global _asgi
    if _asgi is None:
        from mangum import Mangum

        from auth_service.app import app

        _asgi = Mangum(app, lifespan="off")
    return _asgi(event, context)
