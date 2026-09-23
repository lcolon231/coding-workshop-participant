"""A throwaway backend for the browser end-to-end suite.

`frontend/playwright.config.js` starts this as a web server. It creates its own
database, migrates it with the same code the deploy runs, seeds the demo data
with the password in `ACME_SEED_PASSWORD`, and then *becomes* uvicorn serving
every service on one port, exactly as `make serve` does.

`os.execv` rather than a child process: Playwright ends a web server by
killing the process it started, and after the exec that process is uvicorn
itself, so nothing is orphaned holding the port. The database is not dropped
on the way out for the same reason; the next run drops it first, and it is
named so that a leftover is obvious (`acme_e2e_ui`).

Usage: .venv/bin/python tools/e2e_backend.py --port 8100
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_SHARED = _ROOT / "backend" / "_shared"
# The devserver serves every service; its imports resolve like `make serve`.
_PYTHONPATH = os.pathsep.join([str(_SHARED), str(_ROOT / "backend" / "auth")])
_DB_NAME = "acme_e2e_ui"

sys.path.insert(0, str(_SHARED))

from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402

from acme_core.config import get_settings  # noqa: E402
from acme_core.db.migrate import upgrade_head  # noqa: E402
from acme_core.seed import PASSWORD_ENV, seed  # noqa: E402


def _recreate_database() -> str:
    """Drop any earlier copy, create the database, and return its URL."""
    settings = get_settings()
    maintenance = (
        f"postgresql+psycopg://{settings.pg_user}:{settings.pg_pass}"
        f"@{settings.pg_host}:{settings.pg_port}/postgres"
    )
    admin = create_engine(maintenance, isolation_level="AUTOCOMMIT", poolclass=NullPool)
    with admin.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{_DB_NAME}" WITH (FORCE)'))
        conn.execute(text(f'CREATE DATABASE "{_DB_NAME}"'))
    admin.dispose()
    return (
        f"postgresql+psycopg://{settings.pg_user}:{settings.pg_pass}"
        f"@{settings.pg_host}:{settings.pg_port}/{_DB_NAME}"
    )


def _seed(url: str, password: str) -> None:
    """Seed the demo users, facilities and incidents into the new database."""
    from sqlalchemy.orm import sessionmaker

    engine = create_engine(url, poolclass=NullPool, future=True)
    with sessionmaker(bind=engine, future=True)() as session:
        report = seed(session, password)
        session.commit()
    engine.dispose()
    print(f"e2e backend: seeded {report}", file=sys.stderr)  # noqa: T201


def main(argv: list[str] | None = None) -> int:
    """Create, migrate and seed the database, then become uvicorn.

    Returns:
        A process exit code; only reached when the setup refuses to start.
    """
    parser = argparse.ArgumentParser(description="A throwaway backend for the browser e2e suite.")
    parser.add_argument("--port", type=int, default=8100)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args(argv)

    password = os.getenv(PASSWORD_ENV, "")
    if len(password) < 12:
        print(f"set {PASSWORD_ENV} to the seed password (12+ characters)", file=sys.stderr)  # noqa: T201
        return 2

    url = _recreate_database()
    upgrade_head(url)
    _seed(url, password)

    env = dict(os.environ)
    env.update(
        {
            "ACME_PG_NAME": _DB_NAME,
            "ACME_SERVICE_NAME": "all",
            "PYTHONPATH": _PYTHONPATH,
        }
    )
    env.pop("AWS_LAMBDA_FUNCTION_NAME", None)
    command = [
        sys.executable,
        "-m",
        "uvicorn",
        "--factory",
        "tools.devserver:app",
        "--host",
        args.host,
        "--port",
        str(args.port),
        "--log-level",
        "warning",
    ]
    print(f"e2e backend: serving {_DB_NAME} on {args.host}:{args.port}", file=sys.stderr)  # noqa: T201
    os.chdir(_ROOT)
    # The command is fixed above and the interpreter is our own; nothing in it
    # comes from outside this file.
    os.execve(sys.executable, command, env)  # noqa: S606


if __name__ == "__main__":
    raise SystemExit(main())
