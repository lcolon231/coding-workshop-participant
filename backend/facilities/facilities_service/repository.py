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
from sqlalchemy.orm import Session, contains_eager

from acme_core.models import (
    Building,
    Category,
    EngineerProfile,
    Floor,
    Incident,
    IncidentStatus,
    Role,
    Seat,
    User,
)
from acme_core.pagination import like_pattern, paginate
from acme_core.schemas.engineer import EngineerFilters
from acme_core.schemas.facility import (
    BuildingFilters,
    CategoryFilters,
    FloorFilters,
    SeatFilters,
)

_BUILDING_SORTS: Mapping[str, ColumnElement[Any]] = {
    "code": Building.code,
    "name": Building.name,
    "created_at": Building.created_at,
}
_FLOOR_SORTS: Mapping[str, ColumnElement[Any]] = {"level": Floor.level, "name": Floor.name}
_SEAT_SORTS: Mapping[str, ColumnElement[Any]] = {"code": Seat.code, "label": Seat.label}
_CATEGORY_SORTS: Mapping[str, ColumnElement[Any]] = {"name": Category.name}


def _open_assignments() -> ColumnElement[Any]:
    """Non-closed incidents assigned to the engineer of the enclosing row.

    A correlated scalar subquery rather than a second select column: the
    pager keeps only the first column of a statement, and this way the
    count can also be sorted on inside the same statement.
    """
    return (
        select(func.count())
        .select_from(Incident)
        .where(
            Incident.assignee_id == EngineerProfile.user_id,
            Incident.status != IncidentStatus.CLOSED,
        )
        .correlate(EngineerProfile)
        .scalar_subquery()
    )


_ENGINEER_SORTS: Mapping[str, ColumnElement[Any]] = {
    "full_name": User.full_name,
    "specialty": EngineerProfile.specialty,
    "open_assignments": _open_assignments(),
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


# --------------------------------------------------------------------------- floors


def _floors(*, include_inactive: bool) -> Select[Any]:
    """A select over floors, narrowed to active buildings unless told otherwise.

    Floors have no flag of their own: a floor is as visible as its building.
    """
    statement = select(Floor).join(Building)
    if not include_inactive:
        statement = statement.where(Building.is_active.is_(True))
    return statement


def list_floors(
    session: Session, building_id: uuid.UUID, filters: FloorFilters
) -> tuple[list[Floor], int]:
    """Page through one building's floors. The service has already checked the building."""
    statement = select(Floor).where(Floor.building_id == building_id)
    return paginate(
        session,
        statement,
        filters,
        sort_columns=_FLOOR_SORTS,
        sort=filters.sort,
        order=filters.order,
        tiebreaker=Floor.id,
    )


def get_floor(
    session: Session, floor_id: uuid.UUID, *, include_inactive: bool, for_update: bool = False
) -> Floor | None:
    """Fetch one floor the caller may see, optionally locked for the transaction."""
    statement = _floors(include_inactive=include_inactive).where(Floor.id == floor_id)
    if for_update:
        statement = statement.with_for_update(of=Floor)
    return session.execute(statement).scalar_one_or_none()


def count_seats(session: Session, floor_id: uuid.UUID) -> int:
    """How many seats a floor has."""
    return _count(session, select(Seat.id).where(Seat.floor_id == floor_id))


def count_incidents_on_floor(session: Session, floor_id: uuid.UUID) -> int:
    """How many incidents, in any status, name this floor."""
    return _count_incidents(session, Incident.floor_id == floor_id)


# --------------------------------------------------------------------------- seats


def _seats(*, include_inactive: bool) -> Select[Any]:
    """A select over seats, narrowed to active seats in active buildings unless told otherwise."""
    statement = select(Seat).join(Floor).join(Building)
    if not include_inactive:
        statement = statement.where(Seat.is_active.is_(True), Building.is_active.is_(True))
    return statement


def list_seats(
    session: Session, floor_id: uuid.UUID, filters: SeatFilters, *, include_inactive: bool
) -> tuple[list[Seat], int]:
    """Page through one floor's seats. The service has already checked the floor."""
    statement = select(Seat).where(Seat.floor_id == floor_id)
    if not include_inactive:
        statement = statement.where(Seat.is_active.is_(True))
    if filters.search:
        statement = statement.where(_matches((Seat.code, Seat.label), filters.search))
    return paginate(
        session,
        statement,
        filters,
        sort_columns=_SEAT_SORTS,
        sort=filters.sort,
        order=filters.order,
        tiebreaker=Seat.id,
    )


def get_seat(
    session: Session, seat_id: uuid.UUID, *, include_inactive: bool, for_update: bool = False
) -> Seat | None:
    """Fetch one seat the caller may see, optionally locked for the transaction."""
    statement = _seats(include_inactive=include_inactive).where(Seat.id == seat_id)
    if for_update:
        statement = statement.with_for_update(of=Seat)
    return session.execute(statement).scalar_one_or_none()


def count_incidents_at_seat(session: Session, seat_id: uuid.UUID) -> int:
    """How many incidents, in any status, name this seat."""
    return _count_incidents(session, Incident.seat_id == seat_id)


# --------------------------------------------------------------------------- categories


def _categories(*, include_inactive: bool) -> Select[Any]:
    """A select over the categories the caller may see."""
    statement = select(Category)
    if not include_inactive:
        statement = statement.where(Category.is_active.is_(True))
    return statement


def list_categories(
    session: Session, filters: CategoryFilters, *, include_inactive: bool
) -> tuple[list[Category], int]:
    """Page through categories as a flat list; the client builds the tree from parent_id."""
    statement = _categories(include_inactive=include_inactive)
    if filters.roots_only:
        statement = statement.where(Category.parent_id.is_(None))
    if filters.parent_id is not None:
        statement = statement.where(Category.parent_id == filters.parent_id)
    if filters.search:
        statement = statement.where(_matches((Category.name,), filters.search))
    return paginate(
        session,
        statement,
        filters,
        sort_columns=_CATEGORY_SORTS,
        sort=filters.sort,
        order=filters.order,
        tiebreaker=Category.id,
    )


def get_category(
    session: Session, category_id: uuid.UUID, *, include_inactive: bool, for_update: bool = False
) -> Category | None:
    """Fetch one category the caller may see, optionally locked for the transaction."""
    statement = _categories(include_inactive=include_inactive).where(Category.id == category_id)
    if for_update:
        statement = statement.with_for_update()
    return session.execute(statement).scalar_one_or_none()


def root_named(session: Session, name: str, *, excluding: uuid.UUID | None = None) -> bool:
    """Whether a top-level category already carries this name.

    The unique constraint on (parent_id, name) cannot answer this: PostgreSQL
    treats the NULL parent of every root as distinct, so two roots may share
    a name as far as the database is concerned.
    """
    statement = select(Category.id).where(Category.parent_id.is_(None), Category.name == name)
    if excluding is not None:
        statement = statement.where(Category.id != excluding)
    return session.execute(statement.limit(1)).first() is not None


def count_children(session: Session, category_id: uuid.UUID) -> int:
    """How many sub-categories a category has."""
    return _count(session, select(Category.id).where(Category.parent_id == category_id))


def count_incidents_in_category(session: Session, category_id: uuid.UUID) -> int:
    """How many incidents, in any status, carry this category."""
    return _count_incidents(session, Incident.category_id == category_id)


# --------------------------------------------------------------------------- engineers


def _engineers() -> Select[Any]:
    """A select over the profiles of active users who hold the Engineer role.

    The role is checked on the user, not inferred from the profile: a demoted
    engineer keeps their profile row, and an inactive one cannot be assigned
    work, so neither belongs in the assignment picker.
    """
    return (
        select(EngineerProfile)
        .join(User, EngineerProfile.user)
        .options(contains_eager(EngineerProfile.user))
        .where(User.role == Role.ENGINEER, User.is_active.is_(True))
    )


def list_engineers(session: Session, filters: EngineerFilters) -> tuple[list[EngineerProfile], int]:
    """Page through engineers, each with their user loaded."""
    statement = _engineers()
    if filters.specialty is not None:
        statement = statement.where(
            func.lower(EngineerProfile.specialty) == filters.specialty.lower()
        )
    if filters.is_available is not None:
        statement = statement.where(EngineerProfile.is_available.is_(filters.is_available))
    return paginate(
        session,
        statement,
        filters,
        sort_columns=_ENGINEER_SORTS,
        sort=filters.sort,
        order=filters.order,
        tiebreaker=EngineerProfile.user_id,
    )


def get_engineer(
    session: Session, user_id: uuid.UUID, *, for_update: bool = False
) -> EngineerProfile | None:
    """Fetch one engineer's profile by user id, with the user loaded."""
    statement = _engineers().where(EngineerProfile.user_id == user_id)
    if for_update:
        statement = statement.with_for_update(of=EngineerProfile)
    return session.execute(statement).scalar_one_or_none()


def open_assignments_for(session: Session, user_ids: Iterable[uuid.UUID]) -> dict[uuid.UUID, int]:
    """Non-closed incidents per assignee, for one page of engineers in one query."""
    ids = list(user_ids)
    if not ids:
        return {}
    rows = session.execute(
        select(Incident.assignee_id, func.count())
        .where(Incident.assignee_id.in_(ids), Incident.status != IncidentStatus.CLOSED)
        .group_by(Incident.assignee_id)
    ).all()
    return {assignee_id: total for assignee_id, total in rows}
