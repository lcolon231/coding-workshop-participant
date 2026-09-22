"""Programmatic Alembic driver.

Works identically on a developer's machine and inside Lambda. There is no
alembic.ini in any service directory: the Config is built from the installed
package path, so the only thing that has to survive the rsync into a service is
the `migrations/` package itself.

Alembic is imported inside each function rather than at module scope. It pulls
in Mako and MarkupSafe, which the request path never needs and which a 128 MB
Lambda cannot spare (infra/lambda.tf:11).
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING

from acme_core.config import get_settings
from acme_core.logging_config import get_logger

if TYPE_CHECKING:
    from alembic.config import Config

_logger = get_logger(__name__)

# acme_core/db/migrate.py -> acme_core/migrations
_SCRIPT_LOCATION = Path(__file__).resolve().parents[1] / "migrations"


def _build_config(url: str | None = None) -> Config:
    """Build an Alembic Config without reading any ini file.

    Args:
        url: Override the database URL; defaults to the resolved settings.

    Returns:
        A configured `alembic.config.Config`.
    """
    from alembic.config import Config

    config = Config()
    config.set_main_option("script_location", str(_SCRIPT_LOCATION))
    # Config is a ConfigParser: an unescaped '%' in a URL-encoded password is
    # read as interpolation syntax and raises.
    config.set_main_option("sqlalchemy.url", (url or get_settings().database_url).replace("%", "%%"))
    return config


def upgrade_head(url: str | None = None) -> str:
    """Apply every pending migration.

    Args:
        url: Override the database URL.

    Returns:
        The revision now applied.
    """
    from alembic import command

    _logger.info("migration_upgrade_started")
    command.upgrade(_build_config(url), "head")
    current = current_revision(url)
    _logger.info("migration_upgrade_finished", extra={"revision": current})
    return current or ""


def downgrade(revision: str = "base", url: str | None = None) -> str:
    """Revert to a revision.

    Args:
        revision: Target revision; `"base"` reverts everything.
        url: Override the database URL.

    Returns:
        The revision now applied, empty at base.
    """
    from alembic import command

    command.downgrade(_build_config(url), revision)
    return current_revision(url) or ""


def current_revision(url: str | None = None) -> str | None:
    """Return the revision the database is stamped with.

    With no URL this reuses the process-wide engine rather than building a
    private one. Two reasons: the readiness probe would otherwise open a fresh
    connection on every call against a database that scales to zero, and a
    private engine ignores anything that has repointed the shared one -- which
    is how a test would silently query the developer's real database instead of
    its own.

    Args:
        url: Override the database URL. Creates a throwaway engine.

    Returns:
        The revision, or None when no migration has ever run.
    """
    from alembic.migration import MigrationContext

    if url is None:
        from acme_core.db.engine import get_engine

        with get_engine().connect() as connection:
            return MigrationContext.configure(connection).get_current_revision()

    from sqlalchemy import create_engine

    engine = create_engine(url)
    try:
        with engine.connect() as connection:
            return MigrationContext.configure(connection).get_current_revision()
    finally:
        engine.dispose()


def head_revision() -> str | None:
    """Return the newest revision on disk.

    Returns:
        The head revision id.
    """
    from alembic.script import ScriptDirectory

    return ScriptDirectory.from_config(_build_config()).get_current_head()


def migrations_pending(url: str | None = None) -> bool:
    """Report whether the database is behind the migrations on disk.

    Powers the readiness probe, which reports the fact but never applies it --
    a migration triggered by a user request would put DDL on the request path.

    Args:
        url: Override the database URL.

    Returns:
        True when the database is not at head.
    """
    return current_revision(url) != head_revision()


def main(argv: list[str] | None = None) -> int:
    """Run a migration command. Entry point for `python -m acme_core.db.migrate`.

    Args:
        argv: Argument list; defaults to `sys.argv[1:]`.

    Returns:
        A process exit code.
    """
    args = list(argv if argv is not None else sys.argv[1:])
    action = args[0] if args else "upgrade"

    if action == "upgrade":
        print(f"upgraded to {upgrade_head()}")  # noqa: T201
    elif action == "downgrade":
        target = args[1] if len(args) > 1 else "base"
        print(f"downgraded to {downgrade(target) or 'base'}")  # noqa: T201
    elif action == "current":
        print(current_revision() or "none")  # noqa: T201
    elif action == "pending":
        print("yes" if migrations_pending() else "no")  # noqa: T201
    else:
        print(f"unknown action {action!r}", file=sys.stderr)  # noqa: T201
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
