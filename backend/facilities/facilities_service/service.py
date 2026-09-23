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

from acme_core.exceptions import Conflict, NotFound
from acme_core.logging_config import get_logger
from acme_core.models import Building
from acme_core.schemas.common import UpdateModel
from acme_core.schemas.facility import BuildingCreate, BuildingFilters, BuildingUpdate
from acme_core.security.principal import Principal
from facilities_service import repository as repo

_logger = get_logger(__name__)


def _lists_inactive(principal: Principal, filters: Any) -> bool:
    """Whether a list may include retired records: admins who ask, nobody else."""
    return principal.is_admin and bool(filters.include_inactive)


def _plural(count: int, noun: str) -> str:
    return f"{count} {noun}" if count == 1 else f"{count} {noun}s"


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
