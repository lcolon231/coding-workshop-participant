"""Every query the facilities service runs.

Rows are selected, then changed as ORM objects, so each mutation is visible in
one place and nothing bypasses the unit of work (S6). Nothing here decides
who may see what: the service passes the visibility it has already computed
as `include_inactive`, and every read honours it the same way.

Deletes need the counts here because the database will not always refuse
them. `floors.building_id` and `seats.floor_id` cascade, so a building delete
would silently take its floors and seats with it; `incidents.floor_id` and
`incidents.seat_id` are SET NULL, so an incident would silently lose its
location. The service asks first and refuses with a 409 (T72).
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Mapping
from typing import Any

from sqlalchemy import ColumnElement, Select, func, or_, select
from sqlalchemy.orm import Session

from acme_core.models import Building, Floor, Incident, Seat
from acme_core.pagination import like_pattern, paginate
from acme_core.schemas.facility import BuildingFilters

_BUILDING_SORTS: Mapping[str, ColumnElement[Any]] = {
    "code": Building.code,
    "name": Building.name,
    "created_at": Building.created_at,
}


def _matches(columns: Iterable[ColumnElement[Any]], term: str) -> ColumnElement[bool]:
    """A case-insensitive substring match on any of the columns."""
    pattern = like_pattern(term)
    return or_(*(column.ilike(pattern, escape="\\") for column in columns))


def _count(session: Session, statement: Select[Any]) -> int:
    """Count the rows a select would return."""
    return session.execute(
        select(func.count()).select_from(statement.order_by(None).subquery())
    ).scalar_one()


def _count_incidents(session: Session, *criteria: ColumnElement[bool]) -> int:
    """Count the incidents matching every criterion."""
    return _count(session, select(Incident.id).where(*criteria))


# --------------------------------------------------------------------------- buildings


def _buildings(*, include_inactive: bool) -> Select[Any]:
    """A select over the buildings the caller may see."""
    statement = select(Building)
    if not include_inactive:
        statement = statement.where(Building.is_active.is_(True))
    return statement


def list_buildings(
    session: Session, filters: BuildingFilters, *, include_inactive: bool
) -> tuple[list[Building], int]:
    """Page through buildings.

    Args:
        session: The request's session.
        filters: Query parameters.
        include_inactive: Whether retired buildings are part of the result.

    Returns:
        The page and the total visible to this caller.
    """
    statement = _buildings(include_inactive=include_inactive)
    if filters.search:
        statement = statement.where(_matches((Building.code, Building.name), filters.search))
    return paginate(
        session,
        statement,
        filters,
        sort_columns=_BUILDING_SORTS,
        sort=filters.sort,
        order=filters.order,
        tiebreaker=Building.id,
    )


def get_building(
    session: Session,
    building_id: uuid.UUID,
    *,
    include_inactive: bool,
    for_update: bool = False,
) -> Building | None:
    """Fetch one building the caller may see, optionally locked for the transaction."""
    statement = _buildings(include_inactive=include_inactive).where(Building.id == building_id)
    if for_update:
        statement = statement.with_for_update()
    return session.execute(statement).scalar_one_or_none()


def count_floors(session: Session, building_id: uuid.UUID) -> int:
    """How many floors a building has."""
    return _count(session, select(Floor.id).where(Floor.building_id == building_id))


def count_incidents_in_building(session: Session, building_id: uuid.UUID) -> int:
    """How many incidents, in any status, name this building."""
    return _count_incidents(session, Incident.building_id == building_id)


def count_seats(session: Session, floor_id: uuid.UUID) -> int:
    """How many seats a floor has."""
    return _count(session, select(Seat.id).where(Seat.floor_id == floor_id))
