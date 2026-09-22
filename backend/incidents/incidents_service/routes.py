"""HTTP routes for the incidents service, mounted under /api/incidents.

Every handler is a plain `def`: SQLAlchemy is synchronous, and a sync call
inside `async def` would block the event loop for every other request (A6).

Registration order is part of the contract (api.md §4): `/workflow`,
`/escalations` and `/reports/*` must be added **before** any `/{incident_id}`
route, or the typed UUID parameter turns them into a confusing `400`.
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()
