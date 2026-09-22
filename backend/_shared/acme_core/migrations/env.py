"""Alembic environment.

The database URL always comes from `acme_core.config`, never from alembic.ini.
Keeping one derivation means a migration cannot be pointed at the wrong
database by editing a file nobody remembers to check, and the same code path
works on a developer's machine and inside the Lambda.
"""

from __future__ import annotations

from alembic import context
from sqlalchemy import engine_from_config, pool

# Importing the package registers every model on Base.metadata. Without this
# import autogenerate compares against an empty schema and happily emits a
# migration that drops every table.
import acme_core.models  # noqa: F401
from acme_core.config import get_settings
from acme_core.db.base import Base

config = context.config
target_metadata = Base.metadata


def _database_url() -> str:
    """Resolve the URL to migrate, most explicit source first.

    Order matters. `acme_core.db.migrate` builds a Config programmatically and
    puts its caller's URL in `sqlalchemy.url`; reading settings before that
    would silently ignore the argument and migrate whatever the environment
    happens to point at -- which for the test suite is a database that does not
    exist, and in the worst case would be the developer's real one.

    Returns:
        A SQLAlchemy URL.
    """
    override = context.get_x_argument(as_dictionary=True).get("url")
    if override:
        return override
    configured = config.get_main_option("sqlalchemy.url", None)
    if configured:
        # Undo the ConfigParser escaping applied when it was set.
        return configured.replace("%%", "%")
    return get_settings().database_url


def run_migrations_offline() -> None:
    """Emit SQL to stdout without connecting."""
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        # Needed for both: without them autogenerate cannot see a column type
        # change or a server-default change, and silently produces an empty
        # migration.
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Connect and apply migrations."""
    # '%' is escaped because Config is a ConfigParser and would otherwise treat
    # a URL-encoded character in the password as interpolation syntax.
    config.set_main_option("sqlalchemy.url", _database_url().replace("%", "%%"))
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
