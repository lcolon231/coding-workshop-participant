"""The facilities service's rules: what an admin may create, change and remove.

Routes stay thin: they parse, call one function here, and shape the response.
Every decision -- who may see a retired record, which reference must exist,
when a delete is refused because something still depends on the row -- is in
this module, where it can be read in one place and pinned by the tests.

Two rules apply to every resource:

- Non-admins see only active records, and `include_inactive` is honoured for
  admins alone; for anyone else it is ignored rather than refused, so the
  incident form never offers a retired building or seat.
- A delete is refused with a 409 while anything still references the row.
  The database would not always refuse it for us (see repository.py), and
  where it would, the ORM's own cascade runs first, so every delete is
  flushed inside a savepoint that a refusal rolls back whole.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from acme_core.exceptions import Conflict, NotFound, ValidationFailed
from acme_core.logging_config import get_logger
from acme_core.models import Building, Floor, Seat
from acme_core.schemas.common import UpdateModel
from acme_core.schemas.facility import (
    BuildingCreate,
    BuildingFilters,
    BuildingUpdate,
    FloorCreate,
    FloorFilters,
    FloorUpdate,
    SeatCreate,
    SeatFilters,
    SeatUpdate,
)
from acme_core.security.principal import Principal
from facilities_service import repository as repo

_logger = get_logger(__name__)


def _lists_inactive(principal: Principal, filters: Any) -> bool:
    """Whether a list may include retired records: admins who ask, nobody else."""
    return principal.is_admin and bool(filters.include_inactive)


def _plural(count: int, noun: str) -> str:
    return f"{count} {noun}" if count == 1 else f"{count} {noun}s"


def _missing(field: str, message: str) -> ValidationFailed:
    """A 400 naming the body field whose reference could not be resolved."""
    return ValidationFailed(
        "Request validation failed.", details=[{"field": field, "message": message}]
    )


def _apply(row: Any, body: UpdateModel) -> None:
    """Set every field the client sent, including explicit nulls."""
    for field, value in body.changes().items():
        setattr(row, field, value)


def _flush_or_conflict(session: Session, message: str) -> None:
    """Flush inside a savepoint, turning a constraint violation into a 409.

    The savepoint matters: a refused delete has already cascaded to child
    rows inside the ORM, and only rolling back to before the flush restores
    them. The session stays usable for the error response.
    """
    try:
        with session.begin_nested():
            session.flush()
    except IntegrityError as exc:
        raise Conflict(message) from exc


# --------------------------------------------------------------------------- buildings


def _require_building(
    session: Session, principal: Principal, building_id: uuid.UUID, *, for_update: bool = False
) -> Building:
    """Load a building the caller may see, or raise the answer an invisible one gets."""
    building = repo.get_building(
        session, building_id, include_inactive=principal.is_admin, for_update=for_update
    )
    if building is None:
        raise NotFound("Building not found.")
    return building


def list_buildings(
    session: Session, principal: Principal, filters: BuildingFilters
) -> tuple[list[Building], int]:
    """Page through the buildings this caller may see."""
    return repo.list_buildings(
        session, filters, include_inactive=_lists_inactive(principal, filters)
    )


def get_building(session: Session, principal: Principal, building_id: uuid.UUID) -> Building:
    """Fetch one building.

    Raises:
        NotFound: No such building, or it is retired and the caller is not an admin.
    """
    return _require_building(session, principal, building_id)


def create_building(session: Session, body: BuildingCreate) -> Building:
    """Create a building.

    Raises:
        Conflict: The code is already in use.
    """
    building = Building(code=body.code, name=body.name, address=body.address)
    session.add(building)
    _flush_or_conflict(session, "A building with this code already exists.")
    _logger.info("building_created", extra={"building_id": str(building.id)})
    return building


def update_building(
    session: Session, principal: Principal, building_id: uuid.UUID, body: BuildingUpdate
) -> Building:
    """Apply an admin's edits to a building. The code is immutable by schema.

    Raises:
        NotFound: No such building.
    """
    building = _require_building(session, principal, building_id, for_update=True)
    _apply(building, body)
    session.flush()
    return building


def delete_building(session: Session, principal: Principal, building_id: uuid.UUID) -> None:
    """Delete a building nothing depends on.

    The floors foreign key cascades, so without this check a delete would
    silently take every floor and seat with it; the incidents foreign key
    restricts, and that refusal is mapped to the same 409 rather than a 500.

    Raises:
        NotFound: No such building.
        Conflict: It still has floors, or incidents still name it.
    """
    building = _require_building(session, principal, building_id, for_update=True)
    floors = repo.count_floors(session, building.id)
    incidents = repo.count_incidents_in_building(session, building.id)
    if floors or incidents:
        raise Conflict(
            f"Building has {_plural(floors, 'floor')} and {_plural(incidents, 'incident')}; "
            "deactivate it instead."
        )
    session.delete(building)
    _flush_or_conflict(session, "Building is still referenced; deactivate it instead.")
    _logger.info("building_deleted", extra={"building_id": str(building_id)})


# --------------------------------------------------------------------------- floors

_FLOOR_TAKEN = "This building already has a floor at this level."


def _require_floor(
    session: Session, principal: Principal, floor_id: uuid.UUID, *, for_update: bool = False
) -> Floor:
    """Load a floor the caller may see: one whose building is active, unless an admin."""
    floor = repo.get_floor(
        session, floor_id, include_inactive=principal.is_admin, for_update=for_update
    )
    if floor is None:
        raise NotFound("Floor not found.")
    return floor


def list_floors(
    session: Session, principal: Principal, building_id: uuid.UUID, filters: FloorFilters
) -> tuple[list[Floor], int]:
    """Page through a building's floors.

    Raises:
        NotFound: No such building, or it is retired and the caller is not an admin.
    """
    building = _require_building(session, principal, building_id)
    return repo.list_floors(session, building.id, filters)


def get_floor(session: Session, principal: Principal, floor_id: uuid.UUID) -> Floor:
    """Fetch one floor.

    Raises:
        NotFound: No such floor, or its building is retired and the caller is not an admin.
    """
    return _require_floor(session, principal, floor_id)


def create_floor(session: Session, body: FloorCreate) -> Floor:
    """Add a floor to a building.

    Raises:
        ValidationFailed: The building does not exist.
        Conflict: The building already has a floor at this level.
    """
    if repo.get_building(session, body.building_id, include_inactive=True) is None:
        raise _missing("building_id", "Building does not exist.")
    floor = Floor(building_id=body.building_id, level=body.level, name=body.name)
    session.add(floor)
    _flush_or_conflict(session, _FLOOR_TAKEN)
    _logger.info("floor_created", extra={"floor_id": str(floor.id)})
    return floor


def update_floor(
    session: Session, principal: Principal, floor_id: uuid.UUID, body: FloorUpdate
) -> Floor:
    """Apply an admin's edits to a floor. It cannot move to another building.

    Raises:
        NotFound: No such floor.
        Conflict: The new level is already taken in this building.
    """
    floor = _require_floor(session, principal, floor_id, for_update=True)
    _apply(floor, body)
    _flush_or_conflict(session, _FLOOR_TAKEN)
    return floor


def delete_floor(session: Session, principal: Principal, floor_id: uuid.UUID) -> None:
    """Delete a floor nothing depends on.

    The seats foreign key cascades and the incidents one nulls the incident's
    floor, so the database would refuse neither; this check is the only guard.

    Raises:
        NotFound: No such floor.
        Conflict: It still has seats, or incidents still name it.
    """
    floor = _require_floor(session, principal, floor_id, for_update=True)
    seats = repo.count_seats(session, floor.id)
    incidents = repo.count_incidents_on_floor(session, floor.id)
    if seats or incidents:
        raise Conflict(
            f"Floor has {_plural(seats, 'seat')} and {_plural(incidents, 'incident')}; "
            "it cannot be deleted while either remains."
        )
    session.delete(floor)
    _flush_or_conflict(session, "Floor is still referenced and cannot be deleted.")
    _logger.info("floor_deleted", extra={"floor_id": str(floor_id)})


# --------------------------------------------------------------------------- seats

_SEAT_TAKEN = "This floor already has a seat with this code."


def _require_seat(
    session: Session, principal: Principal, seat_id: uuid.UUID, *, for_update: bool = False
) -> Seat:
    """Load a seat the caller may see: active, in an active building, unless an admin."""
    seat = repo.get_seat(
        session, seat_id, include_inactive=principal.is_admin, for_update=for_update
    )
    if seat is None:
        raise NotFound("Seat not found.")
    return seat


def list_seats(
    session: Session, principal: Principal, floor_id: uuid.UUID, filters: SeatFilters
) -> tuple[list[Seat], int]:
    """Page through a floor's seats.

    Raises:
        NotFound: No such floor, or its building is retired and the caller is not an admin.
    """
    floor = _require_floor(session, principal, floor_id)
    return repo.list_seats(
        session, floor.id, filters, include_inactive=_lists_inactive(principal, filters)
    )


def get_seat(session: Session, principal: Principal, seat_id: uuid.UUID) -> Seat:
    """Fetch one seat.

    Raises:
        NotFound: No such seat, or it is retired (or its building is) and the
            caller is not an admin.
    """
    return _require_seat(session, principal, seat_id)


def create_seat(session: Session, body: SeatCreate) -> Seat:
    """Add a seat to a floor.

    Raises:
        ValidationFailed: The floor does not exist.
        Conflict: The floor already has a seat with this code.
    """
    if repo.get_floor(session, body.floor_id, include_inactive=True) is None:
        raise _missing("floor_id", "Floor does not exist.")
    seat = Seat(floor_id=body.floor_id, code=body.code, label=body.label)
    session.add(seat)
    _flush_or_conflict(session, _SEAT_TAKEN)
    _logger.info("seat_created", extra={"seat_id": str(seat.id)})
    return seat


def update_seat(
    session: Session, principal: Principal, seat_id: uuid.UUID, body: SeatUpdate
) -> Seat:
    """Apply an admin's edits to a seat. It cannot move to another floor.

    Raises:
        NotFound: No such seat.
        Conflict: The new code is already taken on this floor.
    """
    seat = _require_seat(session, principal, seat_id, for_update=True)
    _apply(seat, body)
    _flush_or_conflict(session, _SEAT_TAKEN)
    return seat


def delete_seat(session: Session, principal: Principal, seat_id: uuid.UUID) -> None:
    """Delete a seat no incident names.

    The incidents foreign key nulls the seat rather than refusing, so this
    check is the only guard; deactivation is the normal way to retire a seat.

    Raises:
        NotFound: No such seat.
        Conflict: Incidents still name it.
    """
    seat = _require_seat(session, principal, seat_id, for_update=True)
    incidents = repo.count_incidents_at_seat(session, seat.id)
    if incidents:
        raise Conflict(
            f"Seat is referenced by {_plural(incidents, 'incident')}; deactivate it instead."
        )
    session.delete(seat)
    _flush_or_conflict(session, "Seat is still referenced; deactivate it instead.")
    _logger.info("seat_deleted", extra={"seat_id": str(seat_id)})
