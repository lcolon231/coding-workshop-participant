"""HTTP routes for the facilities service, mounted under /api/facilities.

Every handler is a plain `def`: SQLAlchemy is synchronous, and a sync call
inside `async def` would block the event loop for every other request (A6).

Unlike the incidents router there is no static-versus-`{id}` collision to
order around: the nested lists (`/buildings/{id}/floors`, `/floors/{id}/seats`)
have three segments and never compete with `/floors` or `/floors/{id}`. Routes
are simply grouped by resource, in the order api.md §3 lists them.
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()

PREFIX = "/api/facilities"
