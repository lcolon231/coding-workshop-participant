"""Administrative commands run inside the deployed auth Lambda.

Aurora is not publicly reachable, so the only compute that can migrate or seed
it is a Lambda in its VPC. `tools/db.sh` invokes the function synchronously
with `{"source": "acme.admin.v1", "action": ..., "options": {...}}`;
`lambda_entry.classify` has already checked that shape before this runs.
Authorisation is `lambda:InvokeFunction` -- real AWS credentials -- never a
secret on the public Function URL.

Shipped to the auth service only (tools/sync-shared.sh), so there is one door
to a schema change rather than three.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any

from acme_core.logging_config import get_logger

_logger = get_logger(__name__)


class AdminActionRefused(RuntimeError):
    """An admin command was well-formed but not permitted to run."""


def _migrate() -> dict[str, Any]:
    from acme_core.db.engine import dispose_engine
    from acme_core.db.migrate import upgrade_head

    revision = upgrade_head()
    # The next request must not reuse a connection opened against the old schema.
    dispose_engine()
    return {"action": "migrate", "ok": True, "revision": revision}


def _db_current() -> dict[str, Any]:
    from acme_core.db.migrate import current_revision, migrations_pending

    return {
        "action": "db-current",
        "ok": True,
        "revision": current_revision(),
        "pending": migrations_pending(),
    }


def _seed(options: Mapping[str, Any]) -> dict[str, Any]:
    # Confirmation against APP_ID, which only this deployment knows: seeding is
    # production-invocable, and a mistyped function name in someone's shell
    # must not seed a stranger's environment (reviews.md, S2).
    expected = os.getenv("APP_ID", "")
    if not expected or options.get("confirm") != expected:
        raise AdminActionRefused("seed requires options.confirm to equal this deployment's APP_ID")

    password = options.get("admin_password")
    if not isinstance(password, str) or not password:
        raise AdminActionRefused("seed requires options.admin_password; it is never stored in code")

    from acme_core.db.engine import get_session_factory
    from acme_core.seed import seed

    with get_session_factory()() as session:
        report = seed(session, password)
        session.commit()
    return {"action": "seed", "ok": True, **report}


def run_admin_action(action: str, options: Mapping[str, Any]) -> dict[str, Any]:
    """Run one allowlisted administrative command.

    Args:
        action: `migrate`, `seed` or `db-current`.
        options: Action-specific options. Never logged: a seed carries a password.

    Returns:
        A JSON-serialisable summary for the caller of `aws lambda invoke`.

    Raises:
        AdminActionRefused: The action's preconditions were not met.
        ValueError: The action is not allowlisted. Unreachable through
            `classify`, and kept so this function is safe on its own.
    """
    _logger.info("admin_action_started", extra={"action": action})
    if action == "migrate":
        result = _migrate()
    elif action == "db-current":
        result = _db_current()
    elif action == "seed":
        result = _seed(options)
    else:
        raise ValueError(f"unknown admin action {action!r}")
    _logger.info("admin_action_finished", extra={"action": action})
    return result
