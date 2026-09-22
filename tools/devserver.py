"""Local development entrypoint.

Serves the real service application once it exists, and the shared factory's
health endpoints before then, so `make serve` is usable from the first commit
rather than only after the service package lands.

Lambda uses `backend/<service>/function.py`; this file is never deployed.
"""

from __future__ import annotations

import os

from fastapi import FastAPI

from acme_core.api import create_app


def app() -> FastAPI:
    """Build the application uvicorn should serve.

    Returns:
        The service application if its package is importable, otherwise an
        application carrying only the shared health and docs routes.
    """
    service = os.getenv("ACME_SERVICE_NAME", "auth")
    try:
        module = __import__(f"{service}_service.app", fromlist=["app"])
    except ModuleNotFoundError:
        return create_app(service)
    return module.app
