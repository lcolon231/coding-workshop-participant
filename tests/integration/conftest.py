"""Fixtures for tests that need a real PostgreSQL database.

Each run creates a throwaway database, migrates it with the same code
production uses, and rolls every test back inside an outer transaction.

Four hazards are handled deliberately; each is a comment where it applies:

1. The lazy engine is a module global. Anything that opens its own session
   bypasses FastAPI's dependency overrides and would write to the developer's
   real database while the suite still passed.
2. With `join_transaction_mode="create_savepoint"`, an application-side
   `rollback()` discards fixture data set up before the request.
3. `expire_on_commit=False` means assertions read the identity map, not the
   database, so an UPDATE that never reached PostgreSQL still looks applied.
4. `DROP DATABASE ... WITH (FORCE)` cannot terminate the caller's own
   connection, so disposal has to happen before the drop.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Callable, Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Connection, create_engine, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session

from acme_core.config import get_settings
from acme_core.db import engine as engine_module
from acme_core.db.migrate import upgrade_head
from acme_core.models.enums import Role
from acme_core.models.user import EngineerProfile, User

pytestmark = pytest.mark.integration

# Connect to the maintenance database to create and drop others; CREATE DATABASE
# cannot run inside a transaction, hence AUTOCOMMIT.
_MAINTENANCE_URL = "postgresql+psycopg://{user}:{password}@{host}:{port}/postgres"
_TEST_DB_PREFIX = "acme_test_"


def _maintenance_engine() -> Engine:
    """Return an autocommit engine pointed at the maintenance database."""
    settings = get_settings()
    url = _MAINTENANCE_URL.format(
        user=settings.pg_user,
        password=settings.pg_pass,
        host=settings.pg_host,
        port=settings.pg_port,
    )
    return create_engine(url, isolation_level="AUTOCOMMIT", poolclass=None)


def _worker_suffix() -> str:
    """Return a per-worker suffix so parallel runs never share a database."""
    return os.getenv("PYTEST_XDIST_WORKER") or f"pid{os.getpid()}"


@pytest.fixture(scope="session")
def database_url() -> Iterator[str]:
    """Create, migrate and finally drop a throwaway database.

    Migration runs through the real `upgrade_head`, so a broken migration fails
    the suite rather than surfacing later in Aurora.

    Yields:
        The URL of the migrated database.
    """
    settings = get_settings()
    name = f"{_TEST_DB_PREFIX}{_worker_suffix()}"
    admin = _maintenance_engine()

    with admin.connect() as conn:
        # A SIGKILLed run leaks its database. Sweep anything older than this
        # worker's own name before creating, so the disk cannot fill up.
        leaked = conn.execute(
            text(
                "SELECT datname FROM pg_database "
                "WHERE datname LIKE :pattern AND datname <> :current"
            ),
            {"pattern": f"{_TEST_DB_PREFIX}%", "current": name},
        ).scalars()
        for stale in list(leaked):
            conn.execute(text(f'DROP DATABASE IF EXISTS "{stale}" WITH (FORCE)'))
        conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        conn.execute(text(f'CREATE DATABASE "{name}"'))

    url = (
        f"postgresql+psycopg://{settings.pg_user}:{settings.pg_pass}"
        f"@{settings.pg_host}:{settings.pg_port}/{name}"
    )
    # -x url equivalent: env.py prefers an explicit URL over the settings, so
    # the suite can never migrate the developer's database by accident.
    upgrade_head(url)

    yield url

    # Hazard 4: dispose every engine we hold before dropping, or the drop blocks
    # on our own open connection.
    engine_module.dispose_engine()
    with admin.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
    admin.dispose()


@pytest.fixture(scope="session")
def engine(database_url: str) -> Iterator[Engine]:
    """A session-scoped engine bound to the throwaway database."""
    eng = create_engine(database_url, future=True)
    yield eng
    eng.dispose()


@pytest.fixture(autouse=True)
def _guard_global_engine(
    engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> Iterator[None]:
    """Point the module-global engine at the test database.

    Hazard 1. Code that opens its own session -- the seed, admin actions, the
    readiness probe -- never sees a dependency override. Without this it would
    connect to the settings default and write to the developer's database while
    every assertion still passed.
    """
    monkeypatch.setattr(engine_module, "_engine", engine, raising=False)
    monkeypatch.setattr(engine_module, "_session_factory", None, raising=False)
    yield
    engine_module._session_factory = None


@pytest.fixture
def connection(engine: Engine) -> Iterator[Connection]:
    """An open connection wrapped in a transaction that is always rolled back."""
    conn = engine.connect()
    transaction = conn.begin()
    try:
        yield conn
    finally:
        transaction.rollback()
        conn.close()


@pytest.fixture
def db_session(connection: Connection) -> Iterator[Session]:
    """A Session joined to the outer transaction.

    Bound to the *Connection*, never the Engine: binding to the engine makes
    `join_transaction_mode` silently a no-op and every test leaks its data.

    Hazard 2: application code that calls `rollback()` -- the duplicate-email
    path, for instance -- rolls back to the savepoint and discards anything set
    up beforehand. Commit fixture data before issuing the request under test.

    Yields:
        A session whose writes never outlive the test.
    """
    session = Session(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
        future=True,
    )
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def verify_session(connection: Connection) -> Iterator[Session]:
    """A second session for reading back what was written.

    Hazard 3. `expire_on_commit=False` means `db_session` answers from its
    identity map after a commit, so an UPDATE that never reached PostgreSQL
    still reads as applied. This session shares the transaction but has its own
    identity map, so a read here genuinely round-trips.

    Yields:
        A session for assertions about persistence.
    """
    session = Session(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
        future=True,
    )
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(scope="session")
def database_name(database_url: str) -> str:
    """The throwaway database's name, for tests that assert on isolation."""
    return make_url(database_url).database or ""


# --------------------------------------------------------------------------- API clients


@pytest.fixture(autouse=True)
def _cheap_bcrypt(monkeypatch: pytest.MonkeyPatch) -> None:
    """Hash at bcrypt's minimum cost.

    Cost 12 is ~0.3 s per hash; the API suites create dozens of users. Only the
    cost factor changes -- the code path, the salt and the verification are the
    real ones, and verify_password reads the cost from the stored hash.
    """
    from acme_core.security import passwords

    monkeypatch.setattr(passwords, "_ROUNDS", 4)


@pytest.fixture(autouse=True)
def _fresh_jwt_secret() -> Iterator[None]:
    """Forget the cached signing key around each test.

    The key row lives inside the per-test transaction and is rolled back with
    it; a key cached from an earlier test would sign tokens no row backs.
    """
    from acme_core.security.secret import reset_cache

    reset_cache()
    yield
    reset_cache()


def build_client(db_session: Session, service: str, routers: list[Any]) -> TestClient:
    """A TestClient for one service, running every request in the test transaction.

    `get_db` is overridden to yield `db_session` with the same commit/rollback
    semantics as production. Inside a savepoint-joined session a commit only
    releases a savepoint, so nothing outlives the test.
    """
    from acme_core.api import create_app
    from acme_core.db.engine import get_db

    app = create_app(service, routers, configure_logs=False)

    def _override() -> Iterator[Session]:
        try:
            yield db_session
            db_session.commit()
        except Exception:
            db_session.rollback()
            raise

    app.dependency_overrides[get_db] = _override
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def auth_client(db_session: Session) -> TestClient:
    """The auth service, wired to the test transaction."""
    from auth_service.routes import router

    return build_client(db_session, "auth", [router])


class UserFactory:
    """Create committed users, with a known password, for API tests."""

    password = "correct-horse-battery-staple"

    def __init__(self, session: Session) -> None:
        self._session = session
        self._count = 0

    def __call__(
        self,
        role: Role = Role.EMPLOYEE,
        *,
        email: str | None = None,
        full_name: str | None = None,
        specialty: str | None = None,
        **attrs: Any,
    ) -> User:
        from acme_core.security.passwords import hash_password

        self._count += 1
        user = User(
            email=email or f"user{self._count}-{uuid.uuid4().hex[:6]}@acme.inc",
            full_name=full_name or f"User {self._count}",
            password_hash=hash_password(self.password),
            role=role,
            **attrs,
        )
        if role is Role.ENGINEER:
            user.engineer_profile = EngineerProfile(specialty=specialty or "General")
        self._session.add(user)
        # Committed, not flushed: a request that fails rolls back to the last
        # savepoint, and would take uncommitted fixture rows with it (hazard 2).
        self._session.commit()
        return user


@pytest.fixture
def make_user(db_session: Session) -> UserFactory:
    return UserFactory(db_session)


SignIn = Callable[..., dict[str, Any]]


@pytest.fixture
def sign_in(auth_client: TestClient) -> SignIn:
    """Sign in through the real login endpoint and return the token pair."""

    def _sign_in(email: str, password: str = UserFactory.password) -> dict[str, Any]:
        resp = auth_client.post("/api/auth/login", json={"email": email, "password": password})
        assert resp.status_code == 200, resp.text
        return resp.json()

    return _sign_in
