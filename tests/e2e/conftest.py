"""Fixtures that run the real service as a separate process.

The integration tier proves the routes against a real database, but every
request there runs inside one savepoint-joined session that the fixture rolls
back. That design cannot observe the one property a deployment depends on:
that a commit made while answering one request is visible to the next request,
on a different connection, and to anything else that opens the database.

This tier gives that up for fidelity. A throwaway database is created and
migrated exactly as the integration tier does, then `uvicorn` is started as a
child process against it -- the same `tools.devserver:app` factory `make serve`
uses -- and the tests speak HTTP to it. Nothing is overridden or patched
inside the server: bcrypt runs at its real cost, tokens are signed with a key
row the server itself inserted, and every write really commits.

Coverage is deliberately not collected across the process boundary
(plan.md T9): this tier exists to prove persistence, not line counts.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.pool import NullPool

from acme_core.config import get_settings
from acme_core.db.migrate import upgrade_head

pytestmark = pytest.mark.e2e

_ROOT = Path(__file__).resolve().parents[2]
_MAINTENANCE_URL = "postgresql+psycopg://{user}:{password}@{host}:{port}/postgres"
# Distinct from the integration tier's `acme_test_` so the two sweeps never
# drop each other's database mid-run.
_DB_PREFIX = "acme_e2e_"
_SERVICE = "auth"
_READY_TIMEOUT_SECONDS = 30.0


def _maintenance_engine() -> Engine:
    """Return an autocommit engine on the maintenance database.

    CREATE DATABASE cannot run inside a transaction, hence AUTOCOMMIT.
    """
    settings = get_settings()
    url = _MAINTENANCE_URL.format(
        user=settings.pg_user,
        password=settings.pg_pass,
        host=settings.pg_host,
        port=settings.pg_port,
    )
    return create_engine(url, isolation_level="AUTOCOMMIT", poolclass=NullPool)


def _free_port() -> int:
    """Ask the kernel for a port nothing is listening on."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.fixture(scope="session")
def e2e_database() -> Iterator[tuple[str, str]]:
    """Create and migrate a throwaway database; drop it afterwards.

    Yields:
        The database's name and its SQLAlchemy URL.
    """
    settings = get_settings()
    name = f"{_DB_PREFIX}{os.getenv('PYTEST_XDIST_WORKER') or f'pid{os.getpid()}'}"
    admin = _maintenance_engine()

    with admin.connect() as conn:
        # A SIGKILLed run leaks its database; sweep earlier leftovers first.
        leaked = conn.execute(
            text("SELECT datname FROM pg_database WHERE datname LIKE :p AND datname <> :c"),
            {"p": f"{_DB_PREFIX}%", "c": name},
        ).scalars()
        for stale in list(leaked):
            conn.execute(text(f'DROP DATABASE IF EXISTS "{stale}" WITH (FORCE)'))
        conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        conn.execute(text(f'CREATE DATABASE "{name}"'))

    url = (
        f"postgresql+psycopg://{settings.pg_user}:{settings.pg_pass}"
        f"@{settings.pg_host}:{settings.pg_port}/{name}"
    )
    # The same migration code the deploy runs, so the server starts against a
    # schema that `readyz` will accept.
    upgrade_head(url)

    yield name, url

    # WITH (FORCE) terminates the server's pooled connection if the process
    # outlived its fixture; our own engines are NullPool and already closed.
    with admin.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
    admin.dispose()


@pytest.fixture(scope="session")
def server(
    e2e_database: tuple[str, str], tmp_path_factory: pytest.TempPathFactory
) -> Iterator[str]:
    """Run uvicorn against the throwaway database until the session ends.

    Yields:
        The server's base URL, e.g. `http://127.0.0.1:43127`.
    """
    name, _ = e2e_database
    port = _free_port()
    log_path = tmp_path_factory.mktemp("uvicorn") / "server.log"

    env = dict(os.environ)
    env.update(
        {
            "ACME_PG_NAME": name,
            "ACME_SERVICE_NAME": _SERVICE,
            # Source of truth first, exactly as pyproject's pythonpath orders it.
            "PYTHONPATH": os.pathsep.join(
                [str(_ROOT / "backend" / "_shared"), str(_ROOT / "backend" / _SERVICE)]
            ),
        }
    )
    # A stray value would flip the in-Lambda discriminator inside the child.
    env.pop("AWS_LAMBDA_FUNCTION_NAME", None)

    command = [
        sys.executable,
        "-m",
        "uvicorn",
        "--factory",
        "tools.devserver:app",
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
        "--log-level",
        "warning",
    ]
    # The command is fixed above and the interpreter is our own; nothing in it
    # comes from outside the test suite.
    with log_path.open("wb") as log:
        process = subprocess.Popen(  # noqa: S603
            command, cwd=_ROOT, env=env, stdout=log, stderr=subprocess.STDOUT
        )

    base_url = f"http://127.0.0.1:{port}"
    try:
        _wait_until_ready(process, base_url, log_path)
        yield base_url
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


def _wait_until_ready(process: subprocess.Popen[bytes], base_url: str, log_path: Path) -> None:
    """Block until `/readyz` answers 200, or fail with the server's output.

    `readyz` rather than `healthz`: readiness proves the child reached the
    database *and* saw the migrations applied, which is what the tests need.
    """
    deadline = time.monotonic() + _READY_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if process.poll() is not None:
            pytest.fail(
                f"uvicorn exited with {process.returncode} before becoming ready:\n"
                f"{log_path.read_text(errors='replace')}"
            )
        try:
            response = httpx.get(f"{base_url}/api/{_SERVICE}/readyz", timeout=2.0)
            if response.status_code == 200:
                return
        except httpx.TransportError:
            pass
        time.sleep(0.1)
    process.kill()
    pytest.fail(
        f"uvicorn was not ready within {_READY_TIMEOUT_SECONDS:.0f}s:\n"
        f"{log_path.read_text(errors='replace')}"
    )


@pytest.fixture
def client(server: str) -> Iterator[httpx.Client]:
    """An HTTP client bound to the running server.

    Yields:
        A client whose relative paths resolve against the server.
    """
    with httpx.Client(base_url=server, timeout=10.0) as http:
        yield http


RowLookup = Callable[[str], dict[str, Any] | None]


@pytest.fixture
def user_row(e2e_database: tuple[str, str]) -> Iterator[RowLookup]:
    """Read a user row over a brand-new connection each time.

    `NullPool` is the point: every call opens its own connection and closes it,
    so a row it returns was committed by the server, not merely visible inside
    some shared transaction.

    Yields:
        A lookup by email returning the row as a dict, or None.
    """
    _, url = e2e_database
    engine = create_engine(url, poolclass=NullPool, future=True)

    def _lookup(email: str) -> dict[str, Any] | None:
        with engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT id, email, role, is_active, password_hash, sessions_valid_from "
                    "FROM users WHERE email = :email"
                ),
                {"email": email},
            ).mappings().first()
            return dict(row) if row is not None else None

    try:
        yield _lookup
    finally:
        engine.dispose()
