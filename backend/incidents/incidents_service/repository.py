"""Every query the incidents service runs.

Two rules, both structural rather than remembered (S6):

- Every incident query passes through `scope_incidents`, and every child query
  (history, notes, escalations) is narrowed to `visible_incident_ids`, so a row
  outside the caller's scope is filtered out rather than refused. A single-item
  read then ends at `one_or_none()` returning None and the service raises
  NotFound -- there is no branch that could answer 403 and thereby confirm a
  hidden row exists.
- No `session.get()` on a child and no bare `update()` / `delete()`: rows are
  selected, then changed as ORM objects, so each mutation is visible in one
  place and nothing bypasses the unit of work.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Mapping, Sequence
from typing import Any

from sqlalchemy import Row, Select, and_, case, func, or_, select
from sqlalchemy.orm import Session, selectinload
from sqlalchemy.sql.elements import ColumnElement

from acme_core.models import (
    Building,
    Category,
    EscalationRequest,
    EscalationStatus,
    Floor,
    Incident,
    IncidentNote,
    IncidentStatus,
    IncidentStatusHistory,
    Notification,
    NotificationKind,
    Priority,
    Role,
    Seat,
    User,
)
from acme_core.pagination import like_pattern, paginate
from acme_core.reporting import SLA_TARGETS
from acme_core.schemas.common import TimelineParams
from acme_core.schemas.incident import EscalationFilters, IncidentFilters
from acme_core.schemas.notification import NotificationFilters
from acme_core.schemas.report import ReportRange, SlaParams, VolumeParams
from acme_core.scoping import scope_incidents, scope_notes, visible_incident_ids
from acme_core.security.principal import Principal

# Sorting by an enum's display string would put Critical before Low. These
# ranks order priority by urgency and status by lifecycle position instead.
PRIORITY_RANK: Mapping[Priority, int] = {
    Priority.LOW: 0,
    Priority.MEDIUM: 1,
    Priority.HIGH: 2,
    Priority.CRITICAL: 3,
}
_STATUS_RANK: Mapping[IncidentStatus, int] = {
    status: position for position, status in enumerate(IncidentStatus)
}

# Backlog age buckets, oldest boundary last, as api.md I15 names them.
AGE_BUCKETS: Sequence[tuple[str, dt.timedelta | None]] = (
    ("<1d", dt.timedelta(days=1)),
    ("1-3d", dt.timedelta(days=3)),
    ("3-7d", dt.timedelta(days=7)),
    (">7d", None),
)

UNCATEGORISED = "Uncategorised"

_INCIDENT_SORTS: Mapping[str, ColumnElement[Any]] = {
    "created_at": Incident.created_at,
    "priority": case(PRIORITY_RANK, value=Incident.priority),
    "status": case(_STATUS_RANK, value=Incident.status),
    "title": Incident.title,
}

# Summaries are embedded in every row, so the users are loaded in one extra
# query per page rather than one per row (T118).
_INCIDENT_LOADS = (selectinload(Incident.reporter), selectinload(Incident.assignee))
_ESCALATION_LOADS = (
    selectinload(EscalationRequest.requested_by),
    selectinload(EscalationRequest.decided_by),
)


# --------------------------------------------------------------------------- incidents


def _incidents(principal: Principal) -> Select[Any]:
    """A select over the incidents this caller may see, summaries included."""
    return scope_incidents(select(Incident).options(*_INCIDENT_LOADS), principal)


def get_incident(
    session: Session, principal: Principal, incident_id: uuid.UUID, *, for_update: bool = False
) -> Incident | None:
    """Fetch one visible incident, optionally locked for the rest of the transaction.

    Args:
        session: The request's session.
        principal: The caller; determines visibility.
        incident_id: The incident's id.
        for_update: Lock the row so concurrent edits and transitions serialise.

    Returns:
        The incident, or None when it does not exist or is out of scope.
    """
    statement = _incidents(principal).where(Incident.id == incident_id)
    if for_update:
        statement = statement.with_for_update()
    return session.execute(statement).scalar_one_or_none()


def list_incidents(
    session: Session, principal: Principal, filters: IncidentFilters
) -> tuple[list[Incident], int]:
    """Page through visible incidents.

    Every filter is applied after scoping, so none can widen it: an employee
    filtering on another engineer's `assignee_id` still sees only their own.

    Args:
        session: The request's session.
        principal: The caller.
        filters: Query parameters.

    Returns:
        The page and the total visible to this caller.
    """
    statement = _incidents(principal)
    if filters.status is not None:
        statement = statement.where(Incident.status == filters.status)
    if filters.priority is not None:
        statement = statement.where(Incident.priority == filters.priority)
    if filters.building_id is not None:
        statement = statement.where(Incident.building_id == filters.building_id)
    if filters.category_id is not None:
        statement = statement.where(Incident.category_id == filters.category_id)
    if filters.assignee_id is not None:
        statement = statement.where(Incident.assignee_id == filters.assignee_id)
    statement = statement.where(*_created_between(filters.created_from, filters.created_to))
    if filters.search:
        pattern = like_pattern(filters.search)
        statement = statement.where(
            or_(
                Incident.title.ilike(pattern, escape="\\"),
                Incident.description.ilike(pattern, escape="\\"),
            )
        )
    return paginate(
        session,
        statement,
        filters,
        sort_columns=_INCIDENT_SORTS,
        sort=filters.sort,
        order=filters.order,
        tiebreaker=Incident.id,
    )


def add_history(
    session: Session,
    incident: Incident,
    from_status: IncidentStatus | None,
    to_status: IncidentStatus,
    actor_id: uuid.UUID,
    note: str | None,
    at: dt.datetime,
) -> IncidentStatusHistory:
    """Append one row to the audit trail. Flushed with the request.

    `at` is written explicitly rather than left to the column's `now()`
    default: PostgreSQL's `now()` is the transaction start, so two rows
    written in one transaction would tie and the timeline's order would be
    whatever the tiebreaker says. Passing the same instant the stamps use
    also keeps the audit row and `resolved_at` in exact agreement.
    """
    row = IncidentStatusHistory(
        incident_id=incident.id,
        from_status=from_status,
        to_status=to_status,
        actor_id=actor_id,
        note=note,
        created_at=at,
    )
    session.add(row)
    return row


# --------------------------------------------------------------------------- children


def list_history(
    session: Session, principal: Principal, incident_id: uuid.UUID, params: TimelineParams
) -> tuple[list[IncidentStatusHistory], int]:
    """Page through an incident's status changes, reachable only inside scope."""
    statement = (
        select(IncidentStatusHistory)
        .options(selectinload(IncidentStatusHistory.actor))
        .where(
            IncidentStatusHistory.incident_id == incident_id,
            IncidentStatusHistory.incident_id.in_(visible_incident_ids(principal)),
        )
    )
    return paginate(
        session,
        statement,
        params,
        sort_columns={"created_at": IncidentStatusHistory.created_at},
        sort="created_at",
        order=params.order,
        tiebreaker=IncidentStatusHistory.id,
    )


def list_notes(
    session: Session, principal: Principal, incident_id: uuid.UUID, params: TimelineParams
) -> tuple[list[IncidentNote], int]:
    """Page through an incident's notes: inside scope, and internal ones only for staff."""
    statement = scope_notes(
        select(IncidentNote)
        .options(selectinload(IncidentNote.author))
        .where(
            IncidentNote.incident_id == incident_id,
            IncidentNote.incident_id.in_(visible_incident_ids(principal)),
        ),
        principal,
    )
    return paginate(
        session,
        statement,
        params,
        sort_columns={"created_at": IncidentNote.created_at},
        sort="created_at",
        order=params.order,
        tiebreaker=IncidentNote.id,
    )


def list_incident_escalations(
    session: Session, principal: Principal, incident_id: uuid.UUID, params: TimelineParams
) -> tuple[list[EscalationRequest], int]:
    """Page through one incident's escalation requests, inside scope."""
    statement = (
        select(EscalationRequest)
        .options(*_ESCALATION_LOADS)
        .where(
            EscalationRequest.incident_id == incident_id,
            EscalationRequest.incident_id.in_(visible_incident_ids(principal)),
        )
    )
    return paginate(
        session,
        statement,
        params,
        sort_columns={"created_at": EscalationRequest.created_at},
        sort="created_at",
        order=params.order,
        tiebreaker=EscalationRequest.id,
    )


def list_escalations(
    session: Session, principal: Principal, filters: EscalationFilters
) -> tuple[list[EscalationRequest], int]:
    """Page through the escalation queue across every visible incident."""
    statement = (
        select(EscalationRequest)
        .options(*_ESCALATION_LOADS)
        .where(EscalationRequest.incident_id.in_(visible_incident_ids(principal)))
    )
    if filters.status is not None:
        statement = statement.where(EscalationRequest.status == filters.status)
    return paginate(
        session,
        statement,
        filters,
        sort_columns={"created_at": EscalationRequest.created_at},
        sort="created_at",
        order=filters.order,
        tiebreaker=EscalationRequest.id,
    )


def get_escalation_for_update(
    session: Session, principal: Principal, escalation_id: uuid.UUID
) -> EscalationRequest | None:
    """Fetch and lock an escalation together with its incident.

    Joined to a scoped parent rather than fetched by id, and locked with the
    incident because approval changes the incident's priority.
    """
    statement = (
        scope_incidents(
            select(EscalationRequest)
            .join(Incident, EscalationRequest.incident_id == Incident.id)
            .options(*_ESCALATION_LOADS, selectinload(EscalationRequest.incident)),
            principal,
        )
        .where(EscalationRequest.id == escalation_id)
        .with_for_update()
    )
    return session.execute(statement).scalar_one_or_none()


def has_pending_escalation(session: Session, incident_id: uuid.UUID) -> bool:
    """Whether an escalation is already awaiting a decision."""
    statement = select(EscalationRequest.id).where(
        EscalationRequest.incident_id == incident_id,
        EscalationRequest.status == EscalationStatus.PENDING,
    )
    return session.execute(statement.limit(1)).first() is not None


# --------------------------------------------------------------------------- notifications


def active_admin_ids(session: Session) -> list[uuid.UUID]:
    """Every active Facility Admin, the audience for a newly reported incident."""
    return list(
        session.scalars(
            select(User.id).where(User.role == Role.FACILITY_ADMIN, User.is_active.is_(True))
        )
    )


def add_notification(
    session: Session,
    *,
    user_id: uuid.UUID,
    incident: Incident,
    kind: NotificationKind,
    actor_id: uuid.UUID,
    at: dt.datetime,
) -> Notification:
    """Tell one user about one incident. Flushed with the request.

    `at` is explicit for the same reason as `add_history`: `now()` is the
    transaction start, and the bell lists newest first.
    """
    row = Notification(
        user_id=user_id,
        incident_id=incident.id,
        actor_id=actor_id,
        kind=kind,
        incident_title=incident.title,
        created_at=at,
    )
    session.add(row)
    return row


def _own_notifications(principal: Principal) -> Select[Any]:
    """A select over the caller's notifications and nobody else's.

    The recipient filter is applied here, before any caller adds a condition,
    so no query over this table can reach another user's rows.
    """
    return (
        select(Notification)
        .options(selectinload(Notification.actor))
        .where(Notification.user_id == principal.user_id)
    )


def get_notification(
    session: Session, principal: Principal, notification_id: uuid.UUID
) -> Notification | None:
    """Fetch one of the caller's notifications, or None if it is not theirs."""
    statement = _own_notifications(principal).where(Notification.id == notification_id)
    return session.execute(statement).scalar_one_or_none()


def list_notifications(
    session: Session, principal: Principal, filters: NotificationFilters
) -> tuple[list[Notification], int]:
    """Page through the caller's notifications, newest first."""
    statement = _own_notifications(principal)
    if filters.unread:
        statement = statement.where(Notification.read_at.is_(None))
    return paginate(
        session,
        statement,
        filters,
        sort_columns={"created_at": Notification.created_at},
        sort="created_at",
        order="desc",
        tiebreaker=Notification.id,
    )


def count_unread(session: Session, principal: Principal) -> int:
    """How many of the caller's notifications are still unread."""
    statement = select(func.count()).select_from(
        _own_notifications(principal)
        .options()
        .where(Notification.read_at.is_(None))
        .order_by(None)
        .subquery()
    )
    return session.execute(statement).scalar_one()


def unread_notifications(session: Session, principal: Principal) -> list[Notification]:
    """Every unread notification the caller has, to mark them read as ORM rows."""
    statement = _own_notifications(principal).where(Notification.read_at.is_(None))
    return list(session.execute(statement).scalars())


# --------------------------------------------------------------------------- references


def get_building(session: Session, building_id: uuid.UUID) -> Building | None:
    """Fetch a building; buildings are top-level rows readable by everyone."""
    return session.get(Building, building_id)


def get_floor(session: Session, floor_id: uuid.UUID) -> Floor | None:
    """Fetch a floor by id; the service checks it belongs to the named building."""
    return session.get(Floor, floor_id)


def get_seat(session: Session, seat_id: uuid.UUID) -> Seat | None:
    """Fetch a seat by id; the service checks it belongs to the named floor."""
    return session.get(Seat, seat_id)


def get_category(session: Session, category_id: uuid.UUID) -> Category | None:
    """Fetch a category; categories are readable by everyone."""
    return session.get(Category, category_id)


def get_user(session: Session, user_id: uuid.UUID) -> User | None:
    """Fetch a user, for validating an assignee."""
    return session.get(User, user_id)


# --------------------------------------------------------------------------- reports


def _created_between(
    date_from: dt.date | None, date_to: dt.date | None
) -> list[ColumnElement[bool]]:
    """Conditions keeping incidents created on the inclusive dates, in UTC."""
    conditions: list[ColumnElement[bool]] = []
    if date_from is not None:
        start = dt.datetime.combine(date_from, dt.time.min, tzinfo=dt.UTC)
        conditions.append(Incident.created_at >= start)
    if date_to is not None:
        end = dt.datetime.combine(date_to + dt.timedelta(days=1), dt.time.min, tzinfo=dt.UTC)
        conditions.append(Incident.created_at < end)
    return conditions


def _window_conditions(window: ReportRange) -> list[ColumnElement[bool]]:
    """The report's creation window and building filter, as conditions."""
    conditions = _created_between(window.date_from, window.date_to)
    if window.building_id is not None:
        conditions.append(Incident.building_id == window.building_id)
    return conditions


def _window(statement: Select[Any], window: ReportRange) -> Select[Any]:
    """Restrict a select over incidents to the report's creation window."""
    return statement.where(*_window_conditions(window))


def count_by(
    session: Session, window: ReportRange, column: ColumnElement[Any]
) -> dict[Any, int]:
    """Count incidents in the window per distinct value of one column."""
    statement = _window(select(column, func.count(Incident.id)).group_by(column), window)
    return {key: count for key, count in session.execute(statement).all()}


def backlog_by_age(session: Session, window: ReportRange, now: dt.datetime) -> dict[str, int]:
    """Count non-closed incidents in the window by how long they have been open."""
    conditions = [
        (Incident.created_at > now - age, label) for label, age in AGE_BUCKETS if age is not None
    ]
    bucket = case(*conditions, else_=AGE_BUCKETS[-1][0])
    statement = _window(
        select(bucket, func.count(Incident.id))
        .where(Incident.status != IncidentStatus.CLOSED)
        .group_by(bucket),
        window,
    )
    return {label: count for label, count in session.execute(statement).all()}


def _group_column(group_by: str) -> tuple[ColumnElement[Any], Any]:
    """Map a report's `group_by` to a label expression and the join it needs."""
    if group_by == "priority":
        return Incident.priority, None
    if group_by == "status":
        return Incident.status, None
    if group_by == "building":
        return Building.name, Building
    return func.coalesce(Category.name, UNCATEGORISED), Category


def _grouped(statement: Select[Any], joined: Any) -> Select[Any]:
    """Add the join a grouping label requires, if any."""
    if joined is Building:
        return statement.join(Building, Incident.building_id == Building.id)
    if joined is Category:
        return statement.join(Category, Incident.category_id == Category.id, isouter=True)
    return statement


def sla_rows(session: Session, params: SlaParams) -> Sequence[Row[Any]]:
    """Aggregate time-to-acknowledge and time-to-resolve per group.

    One `GROUP BY` over the stamped columns on `incidents`; p90 is
    `percentile_cont`, an ordered-set aggregate that works inside it. Rows a
    stamp is missing on are ignored by the averages, as SQL aggregates do.

    Returns:
        Per group: label, count, resolved count, mean and p90 acknowledge
        seconds, mean and p90 resolve seconds, and how many resolved within
        their priority's target.
    """
    label, joined = _group_column(params.group_by)
    ack = func.extract("epoch", Incident.acknowledged_at - Incident.created_at)
    resolve = func.extract("epoch", Incident.resolved_at - Incident.created_at)
    target = case(
        {priority: int(delta.total_seconds()) for priority, delta in SLA_TARGETS.items()},
        value=Incident.priority,
    )
    within = func.sum(case((Incident.resolved_at.isnot(None) & (resolve <= target), 1), else_=0))
    statement = _grouped(
        select(
            label,
            func.count(Incident.id),
            func.count(Incident.resolved_at),
            func.avg(ack),
            func.percentile_cont(0.9).within_group(ack),
            func.avg(resolve),
            func.percentile_cont(0.9).within_group(resolve),
            within,
        ).select_from(Incident),
        joined,
    )
    statement = _window(statement, params).group_by(label).order_by(label)
    return session.execute(statement).all()


_FINISHED = (IncidentStatus.RESOLVED, IncidentStatus.CLOSED)


def _count_where(condition: ColumnElement[bool]) -> ColumnElement[int]:
    """`COUNT(*) FILTER (WHERE ...)`, spelled so an outer join's empty side counts 0."""
    return func.coalesce(func.sum(case((condition, 1), else_=0)), 0)


def building_rows(session: Session, window: ReportRange) -> Sequence[Row[Any]]:
    """Count incidents in the window per building, busiest first.

    An outer join from `buildings`, with the window on the join rather than
    in `WHERE`, so a building with nothing in the window still appears with
    zeros. Retired buildings appear only while they still have incidents.

    Returns:
        Per building: id, name, is_active, count, open count, critical count.
    """
    total = func.count(Incident.id).label("total")
    statement = (
        select(
            Building.id,
            Building.name,
            Building.is_active,
            total,
            _count_where(Incident.status.notin_(_FINISHED)),
            _count_where(Incident.priority == Priority.CRITICAL),
        )
        .select_from(Building)
        .join(
            Incident,
            and_(Incident.building_id == Building.id, *_window_conditions(window)),
            isouter=True,
        )
        .group_by(Building.id)
        .having(or_(Building.is_active.is_(True), total > 0))
        .order_by(total.desc(), Building.name, Building.id)
    )
    if window.building_id is not None:
        statement = statement.where(Building.id == window.building_id)
    return session.execute(statement).all()


def engineer_rows(session: Session, window: ReportRange) -> Sequence[Row[Any]]:
    """Each engineer's assigned, still-open and completed incidents in the window.

    Same shape as `building_rows`: an outer join from `users` so an idle
    engineer appears with zeros, and a deactivated one only while they still
    hold incidents. "Completed" is Resolved or Closed with a resolution stamp,
    so an incident closed without work (Open -> Closed) counts for nobody.

    Returns:
        Per engineer: id, name, is_active, assigned, open, completed, and the
        mean seconds from report to resolution over the completed ones.
    """
    completed = Incident.status.in_(_FINISHED) & Incident.resolved_at.isnot(None)
    resolve = func.extract("epoch", Incident.resolved_at - Incident.created_at)
    assigned = func.count(Incident.id).label("assigned")
    done = _count_where(completed).label("completed")
    statement = (
        select(
            User.id,
            User.full_name,
            User.is_active,
            assigned,
            _count_where(Incident.status.notin_(_FINISHED)),
            done,
            func.avg(case((completed, resolve))),
        )
        .select_from(User)
        .join(
            Incident,
            and_(Incident.assignee_id == User.id, *_window_conditions(window)),
            isouter=True,
        )
        .where(User.role == Role.ENGINEER)
        .group_by(User.id)
        .having(or_(User.is_active.is_(True), assigned > 0))
        .order_by(done.desc(), assigned.desc(), User.full_name, User.id)
    )
    return session.execute(statement).all()


def volume_rows(session: Session, params: VolumeParams) -> Sequence[Row[Any]]:
    """Count incidents created per interval bucket per group.

    Truncated in UTC explicitly: `date_trunc` on a timestamptz otherwise
    follows the connection's timezone, and a developer's PostgreSQL may not
    run in UTC.
    """
    label, joined = _group_column(params.group_by)
    bucket = func.date_trunc(params.interval, func.timezone("UTC", Incident.created_at))
    statement = _grouped(
        select(bucket, label, func.count(Incident.id)).select_from(Incident), joined
    )
    statement = _window(statement, params).group_by(bucket, label).order_by(bucket, label)
    return session.execute(statement).all()
