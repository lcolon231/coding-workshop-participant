"""Runtime configuration, derived from the platform's injected environment.

The platform injects POSTGRES_HOST/PORT/NAME/USER/PASS into every Lambda
(infra/locals.tf:98-114). The connection string is always built from those; a
hand-set DATABASE_URL is never read, because the two would silently disagree.

One discriminator decides everything environment-dependent: whether we are
running inside Lambda. The runtime sets AWS_LAMBDA_FUNCTION_NAME and a
developer shell does not. IS_LOCAL is deliberately NOT used -- it is injected
only by Terraform, so it is absent locally and the two signals can disagree.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from functools import lru_cache
from urllib.parse import quote_plus

# Hostnames that only resolve from inside a container on the Docker bridge.
# infra/locals.tf:104 injects 172.17.0.1 so a containerised Lambda can reach the
# host's PostgreSQL; from the host itself that address routes nowhere useful.
_CONTAINER_ONLY_HOSTS = frozenset({"172.17.0.1", "host.docker.internal"})

# Defaults mirror the local values in infra/locals.tf:104-108, so host-run
# tooling (alembic, the seed, the test suite) works with zero exported vars.
_DEFAULT_HOST = "localhost"
_DEFAULT_PORT = 5432
_DEFAULT_NAME = "postgres"
_DEFAULT_USER = "postgres"
# The local development password that bin/setup-environment.sh sets on the
# native PostgreSQL. Not a production credential: in the cloud this value is
# always overridden by the injected POSTGRES_PASS (infra/locals.tf:108).
_DEFAULT_PASS = "postgres123"  # nosec B105

_ACCESS_TTL_SECONDS = 30 * 60
_REFRESH_TTL_SECONDS = 7 * 24 * 60 * 60


def in_lambda() -> bool:
    """Return True when running inside the AWS Lambda runtime.

    The runtime always sets AWS_LAMBDA_FUNCTION_NAME; no developer shell does.

    Returns:
        True inside Lambda, False anywhere else.
    """
    return "AWS_LAMBDA_FUNCTION_NAME" in os.environ


@dataclass(frozen=True, slots=True)
class Settings:
    """Fully-resolved settings for one process."""

    running_in_lambda: bool
    pg_host: str
    pg_port: int
    pg_name: str
    pg_user: str
    pg_pass: str
    service_name: str
    access_ttl_seconds: int
    refresh_ttl_seconds: int
    signup_domain: str

    @property
    def database_url(self) -> str:
        """Build the SQLAlchemy URL from the injected PostgreSQL settings.

        Aurora requires TLS; the local PostgreSQL installed by
        bin/setup-environment.sh does not have it enabled, so requesting it
        locally would fail every connection.

        Returns:
            A postgresql+psycopg:// URL including connection parameters.
        """
        base = (
            f"postgresql+psycopg://{quote_plus(self.pg_user)}:{quote_plus(self.pg_pass)}"
            f"@{self.pg_host}:{self.pg_port}/{self.pg_name}"
        )
        params = ["connect_timeout=10", f"application_name=acme-{self.service_name}"]
        if self.running_in_lambda:
            params.append("sslmode=require")
        return f"{base}?{'&'.join(params)}"

    @property
    def safe_database_url(self) -> str:
        """Return `database_url` with the password replaced, for logging.

        Returns:
            The URL with the password substring replaced by `***`.
        """
        return self.database_url.replace(quote_plus(self.pg_pass), "***", 1)

    def jwt_secret_fallback(self) -> str:
        """Derive a deterministic development-only signing key.

        This is NOT the production signing key. The real secret is 32 random
        bytes persisted in `app_secrets` on first use (see the design notes):
        no Lambda environment variable can be added without editing Terraform,
        and deriving a key from POSTGRES_PASS is unsound because
        infra/rds.tf:15 sets the Aurora password to a three-word `random_pet`
        value -- roughly 2**30 candidates, brute-forceable offline against any
        issued token.

        This fallback exists only so local tooling can run before the database
        is reachable. It must never be used when `running_in_lambda` is true.

        Returns:
            A hex digest usable as a local HMAC key.
        """
        material = f"local-dev:{self.service_name}:{self.pg_name}"
        return hashlib.sha256(material.encode()).hexdigest()

    def __repr__(self) -> str:
        """Return a representation with the password masked.

        Returns:
            A repr safe to write to logs or a traceback.
        """
        return (
            f"Settings(service_name={self.service_name!r}, "
            f"running_in_lambda={self.running_in_lambda!r}, "
            f"pg_host={self.pg_host!r}, pg_port={self.pg_port!r}, "
            f"pg_name={self.pg_name!r}, pg_user={self.pg_user!r}, pg_pass='***')"
        )


def _resolve_host(raw_host: str, *, running_in_lambda: bool) -> str:
    """Rewrite a container-only hostname when running on the host.

    Args:
        raw_host: The hostname as injected.
        running_in_lambda: Whether this process is inside the Lambda runtime.

    Returns:
        The hostname this process can actually reach.
    """
    if not running_in_lambda and raw_host in _CONTAINER_ONLY_HOSTS:
        return _DEFAULT_HOST
    return raw_host


def _int_env(name: str, default: int) -> int:
    """Read an integer environment variable, falling back on bad input.

    Args:
        name: Environment variable name.
        default: Value to use when unset or unparseable.

    Returns:
        The parsed integer, or `default`.
    """
    try:
        return int(os.environ[name])
    except (KeyError, ValueError):
        return default


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Build the process-wide settings from the environment.

    Cached, so every caller sees one consistent view. Tests that manipulate the
    environment must call `get_settings.cache_clear()`.

    Returns:
        The resolved `Settings` for this process.
    """
    running_in_lambda = in_lambda()
    raw_host = (os.getenv("POSTGRES_HOST") or _DEFAULT_HOST).strip() or _DEFAULT_HOST
    return Settings(
        running_in_lambda=running_in_lambda,
        # ACME_PG_* are test/CI overrides applied after host resolution, so a
        # test database is never rewritten out from under the suite.
        pg_host=os.getenv("ACME_PG_HOST")
        or _resolve_host(raw_host, running_in_lambda=running_in_lambda),
        pg_port=_int_env("POSTGRES_PORT", _DEFAULT_PORT),
        pg_name=os.getenv("ACME_PG_NAME") or os.getenv("POSTGRES_NAME") or _DEFAULT_NAME,
        pg_user=os.getenv("POSTGRES_USER") or _DEFAULT_USER,
        pg_pass=os.getenv("POSTGRES_PASS") or _DEFAULT_PASS,
        service_name=os.getenv("ACME_SERVICE_NAME", "auth"),
        access_ttl_seconds=_int_env("ACCESS_TTL_SECONDS", _ACCESS_TTL_SECONDS),
        refresh_ttl_seconds=_int_env("REFRESH_TTL_SECONDS", _REFRESH_TTL_SECONDS),
        signup_domain=os.getenv("SIGNUP_DOMAIN", "acme.inc"),
    )
