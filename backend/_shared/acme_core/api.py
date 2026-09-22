"""Application factory shared by every ACME service.

Every service gets identical routing, error handling, logging and probes from
one call, so the three deployments cannot drift apart in the ways a client
would notice.

Routing note: the service directory name *is* the public path prefix.
infra/cloudfront.tf creates one behavior per service, `/api/<name>*`, with no
`origin_path`, so the Lambda receives the full path. The Vite dev proxy
forwards `/api` unrewritten for the same reason. Both environments therefore
deliver `/api/auth/login`, and routes are mounted once.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable, Sequence
from typing import Any

from fastapi import APIRouter, FastAPI, Request, Response

from acme_core import build_stamp
from acme_core.errors import register_exception_handlers
from acme_core.logging_config import (
    configure_logging,
    get_logger,
    new_request_id,
    set_request_id,
)

_logger = get_logger(__name__)

# How long a successful readiness result is trusted. /readyz is unauthenticated
# and reachable on the public Function URL; without this, curling it in a loop
# repeatedly wakes an Aurora cluster that scales to zero capacity.
_READY_CACHE_SECONDS = 30

_ready_cache: tuple[float, bool] = (0.0, False)


def _check_database() -> bool:
    """Open a connection and run the cheapest possible statement.

    Imported lazily so that merely building the app -- or serving /healthz --
    never constructs an engine.

    Returns:
        True when the database answered.
    """
    from sqlalchemy import text

    from acme_core.db.engine import get_engine

    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception:
        _logger.warning("readiness_check_failed", exc_info=True)
        return False
    return True


def _migrations_pending() -> bool | None:
    """Report whether the database is behind the migrations on disk.

    Imported lazily: alembic pulls in Mako and MarkupSafe, which the request
    path never needs and a 128 MB Lambda cannot spare.

    Returns:
        True when behind, False when at head, None when it cannot be determined.
    """
    try:
        from acme_core.db.migrate import migrations_pending

        return migrations_pending()
    except Exception:
        _logger.warning("migration_check_failed", exc_info=True)
        return None


def _database_ready() -> bool:
    """Return cached readiness, refreshing at most every 30 seconds.

    Returns:
        True when the database was reachable within the cache window.
    """
    global _ready_cache
    checked_at, result = _ready_cache
    now = time.monotonic()
    if result and now - checked_at < _READY_CACHE_SECONDS:
        return True
    result = _check_database()
    _ready_cache = (now, result)
    return result


def reset_readiness_cache() -> None:
    """Clear the cached readiness result. Used by tests."""
    global _ready_cache
    _ready_cache = (0.0, False)


def _health_router(service_name: str) -> APIRouter:
    """Build the liveness and readiness routes.

    Args:
        service_name: The service, which is also its path prefix.

    Returns:
        A router to mount under the service prefix.
    """
    router = APIRouter(tags=["health"])

    @router.get("/healthz", summary="Liveness and build provenance")
    def healthz() -> dict[str, Any]:
        """Report that the process is up and which build it is running.

        Deliberately touches no database. A liveness probe that depends on
        Aurora would flap every time the cluster scales to zero.

        Returns:
            Service name and the vendored code's git provenance.
        """
        return {"status": "ok", "service": service_name, "build": build_stamp()}

    @router.get("/readyz", summary="Readiness")
    def readyz(response: Response) -> dict[str, Any]:
        """Report whether the service can serve traffic.

        Reports that migrations are outstanding but never applies them: DDL on
        a user request path would race across concurrent cold starts and put a
        schema change behind an HTTP timeout. A forgotten `make migrate-cloud`
        becomes a loud 503 instead of a mysterious UndefinedTable later.

        Args:
            response: Injected so the status can be set to 503.

        Returns:
            Readiness of each checked dependency.
        """
        ready = _database_ready()
        pending = _migrations_pending() if ready else None
        if not ready or pending:
            response.status_code = 503
        # Booleans only. The Alembic revision maps to a public commit, so
        # serving it would advertise exactly which known issues this
        # deployment carries.
        body: dict[str, Any] = {"database": ready}
        if pending is not None:
            body["migrations_pending"] = pending
        body["status"] = "ready" if ready and not pending else "not_ready"
        return body

    return router


def _install_request_id(app: FastAPI) -> None:
    """Attach a correlation id to every request and response.

    Args:
        app: The application to instrument.
    """

    @app.middleware("http")
    async def _request_id_middleware(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        # Mangum puts the Lambda context here; under uvicorn it is absent and we
        # fall back to a uuid4.
        request_id = new_request_id(request.scope.get("aws.context"))
        set_request_id(request_id)
        # Deliberately NOT cleared in a finally block. Starlette's
        # ServerErrorMiddleware sits outside user middleware, so the 500 handler
        # runs after this coroutine unwinds -- clearing here would strip the
        # correlation id from exactly the responses that need it most. Isolation
        # between requests comes from setting a fresh id on every request, not
        # from clearing the old one.
        response = await call_next(request)
        response.headers["X-Request-Id"] = request_id
        return response


def _use_400_for_validation(app: FastAPI) -> None:
    """Rewrite the documented 422 responses to 400.

    Our handler returns 400 for validation failures, but FastAPI generates the
    schema from its own default of 422. Left alone, the published docs would
    contradict the API's actual behaviour.

    Args:
        app: The application whose schema to patch.
    """
    generate = app.openapi

    def patched() -> dict[str, Any]:
        schema = generate()
        for methods in schema.get("paths", {}).values():
            for operation in methods.values():
                responses = operation.get("responses", {})
                if "422" in responses:
                    responses["400"] = responses.pop("422")
                    responses["400"]["description"] = "Validation Error"
        app.openapi_schema = schema
        return schema

    app.openapi = patched  # type: ignore[method-assign]


def create_app(
    service_name: str,
    routers: Sequence[APIRouter] = (),
    *,
    configure_logs: bool = True,
) -> FastAPI:
    """Build a configured application for one service.

    Args:
        service_name: Service and path prefix, e.g. `"auth"` -> `/api/auth`.
        routers: Routers to mount under that prefix.
        configure_logs: Install the JSON log formatter. Tests disable it to
            keep pytest's capture readable.

    Returns:
        The application.
    """
    if configure_logs:
        configure_logging()

    prefix = f"/api/{service_name}"
    app = FastAPI(
        title=f"ACME Facility Incident Management - {service_name}",
        version="0.1.0",
        # Mounted under the prefix because infra/cloudfront.tf:58 routes only
        # /api/<name>*; at the root these are unreachable in the cloud, and
        # CloudFront rewrites the resulting 404 to index.html with a 200.
        docs_url=f"{prefix}/docs",
        openapi_url=f"{prefix}/openapi.json",
        redoc_url=None,
    )

    # No CORSMiddleware on purpose. Both environments are same-origin (the Vite
    # proxy locally, one CloudFront distribution in the cloud), and
    # infra/lambda.tf:44-51 already sets CORS at the Function URL layer. A
    # second Access-Control-Allow-Origin header makes browsers reject the
    # response outright.

    _install_request_id(app)
    register_exception_handlers(app)
    app.include_router(_health_router(service_name), prefix=prefix)
    for router in routers:
        app.include_router(router, prefix=prefix)
    _use_400_for_validation(app)
    return app
