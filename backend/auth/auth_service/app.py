"""The auth service's ASGI application.

Served by uvicorn locally (`make serve`) and by Mangum in Lambda. Built at
import, but the Lambda handler imports this module only for HTTP events, so an
admin invocation never pays for FastAPI and the route graph (A2).
"""

from __future__ import annotations

from acme_core.api import create_app
from auth_service.routes import router

app = create_app("auth", [router])
