"""HTTP routes for the facilities service, mounted under /api/facilities.

Every handler is a plain `def`: SQLAlchemy is synchronous, and a sync call
inside `async def` would block the event loop for every other request (A6).

Reads take any authenticated caller, because the incident form needs the
building, floor and seat cascade; writes take an admin, and that gate runs
before any row lookup so a 403 never reveals whether the row exists.

Unlike the incidents router there is no static-versus-`{id}` collision to
order around: the nested lists (`/buildings/{id}/floors`, `/floors/{id}/seats`)
have three segments and never compete with `/floors` or `/floors/{id}`. Routes
are simply grouped by resource, in the order api.md §3 lists them.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Query, Response, status

from acme_core.dependencies import AdminPrincipal, CurrentPrincipal, DbSession
from acme_core.errors import error_responses
from acme_core.schemas.common import Page, PageParams
from acme_core.schemas.facility import (
    BuildingCreate,
    BuildingFilters,
    BuildingOut,
    BuildingUpdate,
)
from facilities_service import service

router = APIRouter()

PREFIX = "/api/facilities"


def _page(model: Any, rows: list[Any], total: int, params: PageParams) -> Page[Any]:
    """Shape one page of ORM rows as the response envelope."""
    return Page[model](
        items=[model.model_validate(row) for row in rows],
        total=total,
        limit=params.limit,
        offset=params.offset,
    )


# --------------------------------------------------------------------------- buildings


@router.get(
    "/buildings",
    response_model=Page[BuildingOut],
    responses=error_responses(400, 401),
    tags=["buildings"],
    summary="List buildings",
)
def list_buildings(
    caller: CurrentPrincipal, session: DbSession, filters: Annotated[BuildingFilters, Query()]
) -> Page[BuildingOut]:
    """Active buildings; an admin may ask for retired ones too."""
    rows, total = service.list_buildings(session, caller, filters)
    return _page(BuildingOut, rows, total, filters)


@router.post(
    "/buildings",
    status_code=status.HTTP_201_CREATED,
    response_model=BuildingOut,
    responses=error_responses(400, 401, 403, 409),
    tags=["buildings"],
    summary="Create a building",
)
def create_building(
    body: BuildingCreate, _admin: AdminPrincipal, session: DbSession, response: Response
) -> BuildingOut:
    """Add a building. Its code is printed on signage and cannot change later."""
    building = service.create_building(session, body)
    response.headers["Location"] = f"{PREFIX}/buildings/{building.id}"
    return BuildingOut.model_validate(building)


@router.get(
    "/buildings/{building_id}",
    response_model=BuildingOut,
    responses=error_responses(401, 404),
    tags=["buildings"],
    summary="One building",
)
def get_building(
    building_id: uuid.UUID, caller: CurrentPrincipal, session: DbSession
) -> BuildingOut:
    """A building; retired ones are visible to admins only."""
    return BuildingOut.model_validate(service.get_building(session, caller, building_id))


@router.put(
    "/buildings/{building_id}",
    response_model=BuildingOut,
    responses=error_responses(400, 401, 403, 404),
    tags=["buildings"],
    summary="Update a building",
)
def update_building(
    building_id: uuid.UUID, body: BuildingUpdate, admin: AdminPrincipal, session: DbSession
) -> BuildingOut:
    """Partial update: omitted fields are unchanged, `address: null` clears it."""
    return BuildingOut.model_validate(service.update_building(session, admin, building_id, body))


@router.delete(
    "/buildings/{building_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=error_responses(401, 403, 404, 409),
    tags=["buildings"],
    summary="Delete an empty building",
)
def delete_building(building_id: uuid.UUID, admin: AdminPrincipal, session: DbSession) -> Response:
    """Refused while the building has floors or incidents; deactivate it instead."""
    service.delete_building(session, admin, building_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
