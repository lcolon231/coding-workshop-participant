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
    FloorCreate,
    FloorFilters,
    FloorOut,
    FloorUpdate,
    SeatCreate,
    SeatFilters,
    SeatOut,
    SeatUpdate,
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


# --------------------------------------------------------------------------- floors


@router.get(
    "/buildings/{building_id}/floors",
    response_model=Page[FloorOut],
    responses=error_responses(400, 401, 404),
    tags=["floors"],
    summary="A building's floors",
)
def list_floors(
    building_id: uuid.UUID,
    caller: CurrentPrincipal,
    session: DbSession,
    filters: Annotated[FloorFilters, Query()],
) -> Page[FloorOut]:
    """Floors of one building, lowest level first. A retired building is 404 to non-admins."""
    rows, total = service.list_floors(session, caller, building_id, filters)
    return _page(FloorOut, rows, total, filters)


@router.post(
    "/floors",
    status_code=status.HTTP_201_CREATED,
    response_model=FloorOut,
    responses=error_responses(400, 401, 403, 409),
    tags=["floors"],
    summary="Create a floor",
)
def create_floor(
    body: FloorCreate, _admin: AdminPrincipal, session: DbSession, response: Response
) -> FloorOut:
    """Add a floor. Levels are signed, so basements are negative."""
    floor = service.create_floor(session, body)
    response.headers["Location"] = f"{PREFIX}/floors/{floor.id}"
    return FloorOut.model_validate(floor)


@router.get(
    "/floors/{floor_id}",
    response_model=FloorOut,
    responses=error_responses(401, 404),
    tags=["floors"],
    summary="One floor",
)
def get_floor(floor_id: uuid.UUID, caller: CurrentPrincipal, session: DbSession) -> FloorOut:
    """A floor; those of a retired building are visible to admins only."""
    return FloorOut.model_validate(service.get_floor(session, caller, floor_id))


@router.put(
    "/floors/{floor_id}",
    response_model=FloorOut,
    responses=error_responses(400, 401, 403, 404, 409),
    tags=["floors"],
    summary="Update a floor",
)
def update_floor(
    floor_id: uuid.UUID, body: FloorUpdate, admin: AdminPrincipal, session: DbSession
) -> FloorOut:
    """Partial update of level or name. Moving a floor to another building is not supported."""
    return FloorOut.model_validate(service.update_floor(session, admin, floor_id, body))


@router.delete(
    "/floors/{floor_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=error_responses(401, 403, 404, 409),
    tags=["floors"],
    summary="Delete an empty floor",
)
def delete_floor(floor_id: uuid.UUID, admin: AdminPrincipal, session: DbSession) -> Response:
    """Refused while the floor has seats or incidents name it."""
    service.delete_floor(session, admin, floor_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --------------------------------------------------------------------------- seats


@router.get(
    "/floors/{floor_id}/seats",
    response_model=Page[SeatOut],
    responses=error_responses(400, 401, 404),
    tags=["seats"],
    summary="A floor's seats",
)
def list_seats(
    floor_id: uuid.UUID,
    caller: CurrentPrincipal,
    session: DbSession,
    filters: Annotated[SeatFilters, Query()],
) -> Page[SeatOut]:
    """Active seats of one floor; an admin may ask for retired ones too."""
    rows, total = service.list_seats(session, caller, floor_id, filters)
    return _page(SeatOut, rows, total, filters)


@router.post(
    "/seats",
    status_code=status.HTTP_201_CREATED,
    response_model=SeatOut,
    responses=error_responses(400, 401, 403, 409),
    tags=["seats"],
    summary="Create a seat",
)
def create_seat(
    body: SeatCreate, _admin: AdminPrincipal, session: DbSession, response: Response
) -> SeatOut:
    """Add a seat. Codes repeat between floors but not within one."""
    seat = service.create_seat(session, body)
    response.headers["Location"] = f"{PREFIX}/seats/{seat.id}"
    return SeatOut.model_validate(seat)


@router.get(
    "/seats/{seat_id}",
    response_model=SeatOut,
    responses=error_responses(401, 404),
    tags=["seats"],
    summary="One seat",
)
def get_seat(seat_id: uuid.UUID, caller: CurrentPrincipal, session: DbSession) -> SeatOut:
    """A seat; retired ones, and those in retired buildings, are visible to admins only."""
    return SeatOut.model_validate(service.get_seat(session, caller, seat_id))


@router.put(
    "/seats/{seat_id}",
    response_model=SeatOut,
    responses=error_responses(400, 401, 403, 404, 409),
    tags=["seats"],
    summary="Update a seat",
)
def update_seat(
    seat_id: uuid.UUID, body: SeatUpdate, admin: AdminPrincipal, session: DbSession
) -> SeatOut:
    """Partial update of code, label or active flag. Moving a seat is not supported."""
    return SeatOut.model_validate(service.update_seat(session, admin, seat_id, body))


@router.delete(
    "/seats/{seat_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=error_responses(401, 403, 404, 409),
    tags=["seats"],
    summary="Delete an unused seat",
)
def delete_seat(seat_id: uuid.UUID, admin: AdminPrincipal, session: DbSession) -> Response:
    """Refused while incidents name the seat; deactivate it instead."""
    service.delete_seat(session, admin, seat_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
