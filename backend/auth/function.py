"""AWS Lambda entrypoint for the auth service.

`infra/locals.tf:57` hardcodes the handler as `function.handler`, so both this
module's name and the function's name are load-bearing.

The web stack is imported here, at module scope, on purpose. Lambda runs a
module's import during its init phase, which gets a full CPU regardless of
memory size; the invoke phase gets a fraction of one. The first deploy
measured the difference: with the import deferred into the handler, every
cold environment spent 12 s (at 512 MB; 45-60 s at 128 MB) compiling the
850-odd source files of FastAPI, SQLAlchemy and pydantic inside the request,
because the package ships no bytecode (the packager installs with
`--no-compile`). The lazy form was A2's answer to a 128 MB ceiling that
infra/lambda.tf no longer has; Alembic is still imported only by the admin
branch. Anything unrecognised is refused rather than handed to Mangum (S11).
"""

from __future__ import annotations

from typing import Any

from mangum import Mangum

from acme_core.lambda_entry import classify
from acme_core.logging_config import get_logger
from auth_service.app import app

_logger = get_logger(__name__)

# The adapter is still built on the first HTTP event, so an admin invocation
# never constructs one; the imports above are the expensive part.
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
        _asgi = Mangum(app, lifespan="off")
    return _asgi(event, context)
