"""Local development entrypoint.

`make serve` runs every service in one uvicorn process, so the browser sees
what CloudFront gives it in the cloud: one origin answering `/api/auth`,
`/api/incidents` and the rest. The Vite proxy forwards `/api` to one port
unrewritten, so without this the first request to a second service would
land on the wrong Lambda's local twin and 404.

Each service is still built by its own `create_app`, exactly as its Lambda
builds it, and a tiny ASGI dispatcher picks the application by path prefix.
Nothing is shared between them at runtime beyond the process, which matches
the deployment: three functions, one database, no HTTP calls between them.

`/api/docs` is one Swagger page over every service, backed by
`/api/openapi.json`, a merge of the per-service schemas. Local only: in the
cloud nothing answers at `/api/docs`, because CloudFront routes only
`/api/<service>*`, so the per-service pages remain the deployed docs.

`ACME_SERVICE_NAME=<service>` runs just that one, the Lambda-faithful mode the
end-to-end tests use. A service directory whose package does not exist yet is
served with only the shared health and docs routes, so `make serve` is usable
from the first commit rather than only after the package lands.

Lambda uses `backend/<service>/function.py`; this file is never deployed.
"""

from __future__ import annotations

import copy
import importlib
import json
import os
import sys
from collections.abc import Awaitable, Callable, Mapping, MutableMapping
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import HTMLResponse

from acme_core.api import create_app

_ROOT = Path(__file__).resolve().parents[1]
_BACKEND = _ROOT / "backend"

ALL = "all"
COMBINED_TITLE = "ACME Facility Incident Management - all services"
COMBINED_DOCS_URL = "/api/docs"
COMBINED_OPENAPI_URL = "/api/openapi.json"

Scope = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[MutableMapping[str, Any]]]
Send = Callable[[MutableMapping[str, Any]], Awaitable[None]]
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]


def discover_services() -> list[str]:
    """Name every deployable service directory.

    Same rule as infra/locals.tf and tools/sync-shared.sh: a directory one
    level under backend/ holding requirements.txt, skipping `_` and `.`
    prefixes, so what runs locally is what Terraform would deploy.

    Returns:
        Service names in sorted order.
    """
    return sorted(
        path.parent.name
        for path in _BACKEND.glob("*/requirements.txt")
        if not path.parent.name.startswith(("_", "."))
    )


def load_service(service: str) -> FastAPI:
    """Build one service's application, importing it from its own directory.

    Args:
        service: The directory name under backend/, e.g. `"auth"`.

    Returns:
        The service's app, or a shell with only the shared routes when its
        package does not exist yet.
    """
    service_dir = str(_BACKEND / service)
    if service_dir not in sys.path:
        sys.path.append(service_dir)
    try:
        module = importlib.import_module(f"{service}_service.app")
    except ModuleNotFoundError:
        return create_app(service)
    return module.app


def _rewrite_refs(node: Any, renames: Mapping[str, str]) -> Any:
    """Return `node` with `#/components/schemas/<old>` references renamed."""
    if isinstance(node, dict):
        return {key: _rewrite_refs(value, renames) for key, value in node.items()}
    if isinstance(node, list):
        return [_rewrite_refs(item, renames) for item in node]
    if isinstance(node, str) and node.startswith("#/components/schemas/"):
        name = node.rsplit("/", 1)[1]
        return f"#/components/schemas/{renames[name]}" if name in renames else node
    return node


def merge_openapi(apps: Mapping[str, FastAPI]) -> dict[str, Any]:
    """Combine every service's OpenAPI document into one.

    Paths never collide: each service owns its prefix. Component schemas are
    shared by name when their definitions are identical -- the health and
    error envelopes every service emits -- and a same-named schema with a
    different definition is renamed `<Service><Name>` in that service's
    document, references included, so nothing is silently overwritten. Every
    operation's tags are prefixed with the service name, so Swagger groups
    the page by service.

    Args:
        apps: Service name to its application, in display order.

    Returns:
        An OpenAPI 3 document.
    """
    merged: dict[str, Any] = {
        "openapi": "3.1.0",
        "info": {"title": COMBINED_TITLE, "version": "0.1.0"},
        "paths": {},
        "components": {"schemas": {}, "securitySchemes": {}},
        "tags": [],
    }
    schemas: dict[str, Any] = merged["components"]["schemas"]
    seen_tags: list[str] = []

    for service, app in apps.items():
        document = copy.deepcopy(app.openapi())
        merged["openapi"] = document.get("openapi", merged["openapi"])
        components = document.get("components", {})

        renames: dict[str, str] = {}
        for name, definition in components.get("schemas", {}).items():
            if name in schemas and schemas[name] != definition:
                renames[name] = f"{service.capitalize()}{name}"
        document = _rewrite_refs(document, renames)
        for name, definition in document.get("components", {}).get("schemas", {}).items():
            schemas.setdefault(renames.get(name, name), definition)
        merged["components"]["securitySchemes"].update(components.get("securitySchemes", {}))

        for path, operations in document.get("paths", {}).items():
            for operation in operations.values():
                if isinstance(operation, dict):
                    tags = [f"{service}: {tag}" for tag in operation.get("tags") or ["default"]]
                    operation["tags"] = tags
                    seen_tags.extend(tag for tag in tags if tag not in seen_tags)
            merged["paths"][path] = operations

    merged["tags"] = [{"name": tag} for tag in seen_tags]
    return merged


def build_portal(apps: Mapping[str, FastAPI]) -> FastAPI:
    """The combined docs page and its schema, as a small application.

    Args:
        apps: Service name to its application.

    Returns:
        An application answering only the two combined-docs paths.
    """
    portal = FastAPI(title=COMBINED_TITLE, docs_url=None, redoc_url=None, openapi_url=None)
    cache: dict[str, Any] = {}

    @portal.get(COMBINED_OPENAPI_URL, include_in_schema=False)
    def openapi() -> dict[str, Any]:
        if not cache:
            cache["document"] = merge_openapi(apps)
        return cache["document"]

    @portal.get(COMBINED_DOCS_URL, include_in_schema=False)
    def docs() -> HTMLResponse:
        return get_swagger_ui_html(openapi_url=COMBINED_OPENAPI_URL, title=COMBINED_TITLE)

    return portal


class Dispatcher:
    """Route each request to the service that owns its `/api/<name>` prefix.

    Deliberately not Starlette's `Mount`: mounting strips the prefix from the
    path, and every service's routes expect the full `/api/<name>/...`
    because that is what the Lambda receives.
    """

    def __init__(self, apps: Mapping[str, FastAPI]) -> None:
        """Remember the applications by service name.

        Args:
            apps: Service name to its application.
        """
        self._apps = dict(apps)
        self._portal = build_portal(self._apps)

    def _match(self, path: str) -> ASGIApp | None:
        if path in (COMBINED_DOCS_URL, COMBINED_OPENAPI_URL):
            return self._portal
        for name, app in self._apps.items():
            prefix = f"/api/{name}"
            if path == prefix or path.startswith(f"{prefix}/"):
                return app
        return None

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Dispatch one ASGI event.

        Args:
            scope: The connection scope.
            receive: The ASGI receive channel.
            send: The ASGI send channel.
        """
        if scope["type"] == "lifespan":
            # The services run lifespan="off" in Lambda; nothing to start here.
            while True:
                message = await receive()
                if message["type"] == "lifespan.startup":
                    await send({"type": "lifespan.startup.complete"})
                elif message["type"] == "lifespan.shutdown":
                    await send({"type": "lifespan.shutdown.complete"})
                    return

        app = self._match(scope.get("path", ""))
        if app is not None:
            await app(scope, receive, send)
            return

        # The same envelope every service uses, so a client cannot tell the
        # dispatcher's 404 from a service's.
        body = json.dumps(
            {
                "error": "not_found",
                "message": "No service is mounted at this path.",
                "details": [],
                "request_id": None,
            }
        ).encode()
        await send(
            {
                "type": "http.response.start",
                "status": 404,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode()),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})


def app() -> ASGIApp:
    """Build the application uvicorn should serve.

    Returns:
        A dispatcher over every discovered service, or, when
        `ACME_SERVICE_NAME` names one, that service's application alone.
    """
    service = os.getenv("ACME_SERVICE_NAME", ALL)
    if service != ALL:
        return load_service(service)
    return Dispatcher({name: load_service(name) for name in discover_services()})
