"""The JWT signing key.

No Lambda environment variable can be added without editing Terraform, and
`local.env_vars` in infra/locals.tf has no slot for a secret. The obvious
workaround -- deriving a key from POSTGRES_PASS -- is unsound: infra/rds.tf:15
sets the Aurora master password to `random_pet.this.id`, and infra/main.tf:9-11
configures that with length = 3. A three-word pet name is roughly 2**30
candidates against a single unsalted hash, and a JWT signature is verifiable
offline, so anyone able to self-register could recover the signing key in
minutes -- and the Aurora password with it.

So the key is generated once, at 32 random bytes, and kept in the database
every service already shares.
"""

from __future__ import annotations

import secrets
import threading

from sqlalchemy import text
from sqlalchemy.orm import Session

from acme_core.logging_config import get_logger

_logger = get_logger(__name__)

# The row's primary key, not a credential. bandit B105 matches on the variable
# name; the value it guards is generated at runtime and never appears in source.
SECRET_NAME = "jwt_hs256"  # nosec B105
_SECRET_BYTES = 32

_cached: str | None = None
_lock = threading.Lock()


def _read(session: Session) -> str | None:
    """Return the stored secret, or None when it has never been written."""
    return session.execute(
        text("SELECT value FROM app_secrets WHERE name = :name"),
        {"name": SECRET_NAME},
    ).scalar_one_or_none()


def get_jwt_secret(session: Session) -> str:
    """Return the signing key, creating it on first use.

    Cached in a module global, so a warm execution environment pays one query
    per cold start rather than one per request.

    The write is `ON CONFLICT DO NOTHING` followed by a re-read rather than an
    insert-then-use: two cold Lambdas can reach this at the same moment, and
    whichever loses the race must end up with the winner's key, not its own.

    Args:
        session: An open session against the application database.

    Returns:
        The signing key.
    """
    global _cached
    if _cached is not None:
        return _cached

    with _lock:
        if _cached is not None:
            return _cached

        existing = _read(session)
        if existing is None:
            session.execute(
                text(
                    "INSERT INTO app_secrets (name, value, created_at, updated_at) "
                    "VALUES (:name, :value, now(), now()) "
                    "ON CONFLICT (name) DO NOTHING"
                ),
                {"name": SECRET_NAME, "value": secrets.token_urlsafe(_SECRET_BYTES)},
            )
            session.commit()
            # Re-read: a concurrent writer may have won, and its value is the
            # one every other process will already be using.
            existing = _read(session)
            _logger.info("jwt_secret_provisioned")

        if existing is None:  # pragma: no cover - only if the row vanished mid-flight
            raise RuntimeError("could not provision the JWT signing secret")
        _cached = existing
    return _cached


def reset_cache() -> None:
    """Forget the cached secret. Used by tests and after a rotation."""
    global _cached
    _cached = None
