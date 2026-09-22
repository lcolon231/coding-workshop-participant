"""Lazily-constructed SQLAlchemy engine and session factory.

The engine is built on first use rather than at import. A Lambda cold start
imports this module long before it knows whether the invocation will touch the
database at all -- an admin `migrate` action, for instance, builds its own
connection -- and opening a pool at import would spend cold-start time and
memory on a connection that may never be used.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from acme_core.config import Settings, get_settings

# A Lambda execution environment serves one request at a time, so a second
# pooled connection is waste. Under uvicorn, sync endpoints run in a threadpool,
# which is why the builder below is locked.
_POOL_SIZE = 1
# Frozen Lambda containers hold TCP connections that the far side has dropped;
# recycle below the common 5-minute idle timeout.
_POOL_RECYCLE_SECONDS = 280

_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None
_lock = threading.Lock()


def get_engine(settings: Settings | None = None) -> Engine:
    """Return the process-wide engine, creating it on first use.

    Args:
        settings: Override settings; defaults to `get_settings()`.

    Returns:
        The cached `Engine`.
    """
    global _engine
    if _engine is None:
        with _lock:
            # Re-check: another thread may have built it while we waited.
            if _engine is None:
                cfg = settings or get_settings()
                _engine = create_engine(
                    cfg.database_url,
                    pool_size=_POOL_SIZE,
                    max_overflow=0,
                    # Fail fast rather than block for SQLAlchemy's 30s default;
                    # the caller is inside a request with its own deadline.
                    pool_timeout=5,
                    # Aurora Serverless v2 scales to zero capacity
                    # (infra/rds.tf:27) and drops idle connections.
                    pool_pre_ping=True,
                    pool_recycle=_POOL_RECYCLE_SECONDS,
                    future=True,
                )
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    """Return the process-wide session factory, creating it on first use.

    `expire_on_commit=False` so an ORM object stays readable after the endpoint
    commits and FastAPI can still serialise it.

    Returns:
        The cached `sessionmaker`.
    """
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(
            bind=get_engine(),
            expire_on_commit=False,
            future=True,
        )
    return _session_factory


def get_db() -> Iterator[Session]:
    """Yield a request-scoped session, committing on success.

    Used as a FastAPI dependency. Integration tests override it with a session
    bound to an externally-managed transaction.

    Yields:
        A `Session` for the duration of one request.
    """
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def dispose_engine() -> None:
    """Drop the cached engine and factory.

    Tests call this between databases, and the admin actions call it after a
    migration so the next caller does not reuse a connection opened against the
    pre-migration schema.
    """
    global _engine, _session_factory
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _session_factory = None
