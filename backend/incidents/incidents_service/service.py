"""The incidents service's rules: who may do what to which incident, and when.

Routes stay thin: they parse, call one function here, and shape the response.
Every decision -- reference validation, field-level edit rights, the order
of the transition checks, escalation eligibility -- is in this module, where
it can be read in one place and pinned by the integration tests.

Status moves only through `transition`, which defers to `acme_core.workflow`.
Nothing here branches on a status name to decide legality; the tables there
do, and adding an edge is a change to data, not to this file.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Mapping
from typing import Any, Final

from sqlalchemy.orm import Session

from acme_core.exceptions import Conflict, Forbidden, NotFound, ValidationFailed
from acme_core.logging_config import get_logger
from acme_core.models import (
    EscalationRequest,
    EscalationStatus,
    Incident,
    IncidentNote,
    IncidentStatus,
    IncidentStatusHistory,
    NoteVisibility,
    Notification,
    NotificationKind,
    Priority,
    Role,
    User,
)
from acme_core.reporting import SLA_TARGETS
from acme_core.schemas.common import TimelineParams
from acme_core.schemas.incident import (
    EscalationCreate,
    EscalationDecision,
    EscalationFilters,
    IncidentCreate,
    IncidentFilters,
    IncidentUpdate,
    NoteCreate,
    TransitionOption,
    TransitionRequest,
)
from acme_core.schemas.notification import NotificationFilters
from acme_core.schemas.report import (
    BuildingRow,
    BuildingsReport,
    CountBucket,
    EngineerRow,
    EngineersReport,
    ReportRange,
    SlaParams,
    SlaReport,
    SlaRow,
    SlaTarget,
    SummaryReport,
    VolumeParams,
    VolumeReport,
    VolumeRow,
)
from acme_core.security.principal import Principal
from acme_core.workflow import (
    STAMP_ON_ENTER,
    TRANSITIONS,
    TransitionContext,
    can_transition,
    stamps_for,
    validate_transition,
)
from incidents_service import repository as repo

_logger = get_logger(__name__)

# Which fields each relationship to an incident may edit through PUT (api.md I4).
_ADMIN_EDITABLE: Final[frozenset[str]] = frozenset(
    {"title", "description", "priority", "category_id", "assignee_id"}
)
_REPORTER_EDITABLE_WHILE_OPEN: Final[frozenset[str]] = frozenset(
    {"title", "description", "category_id"}
)

# Approval raises priority exactly one level; Critical has nowhere to go.
_NEXT_PRIORITY: Final[Mapping[Priority, Priority]] = {
    Priority.LOW: Priority.MEDIUM,
    Priority.MEDIUM: Priority.HIGH,
    Priority.HIGH: Priority.CRITICAL,
}

_STAMP_FIELDS: Final[frozenset[str]] = frozenset(
    field for fields in STAMP_ON_ENTER.values() for field in fields
)


def _now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def _detail(field: str, message: str) -> dict[str, str]:
    return {"field": field, "message": message}


def _require(session: Session, principal: Principal, incident_id: uuid.UUID, **kw: Any) -> Incident:
    """Load a visible incident or raise the one answer an invisible one gets."""
    incident = repo.get_incident(session, principal, incident_id, **kw)
    if incident is None:
        raise NotFound("Incident not found.")
    return incident


def _context(principal: Principal, incident: Incident) -> TransitionContext:
    return TransitionContext(
        current=incident.status,
        actor_id=principal.user_id,
        actor_role=principal.role,
        reporter_id=incident.reporter_id,
        assignee_id=incident.assignee_id,
    )


# --------------------------------------------------------------------------- references


def _check_location(
    session: Session,
    building_id: uuid.UUID,
    floor_id: uuid.UUID | None,
    seat_id: uuid.UUID | None,
) -> list[dict[str, str]]:
    """Validate that the building, floor and seat exist and nest correctly."""
    details: list[dict[str, str]] = []
    building = repo.get_building(session, building_id)
    if building is None or not building.is_active:
        details.append(_detail("building_id", "Building does not exist or is not active."))
    floor = repo.get_floor(session, floor_id) if floor_id is not None else None
    if floor_id is not None and (floor is None or floor.building_id != building_id):
        details.append(_detail("floor_id", "Floor does not exist in this building."))
    if seat_id is not None:
        seat = repo.get_seat(session, seat_id)
        if seat is None or not seat.is_active or floor is None or seat.floor_id != floor.id:
            details.append(_detail("seat_id", "Seat does not exist on this floor."))
    return details


def _check_category(session: Session, category_id: uuid.UUID | None) -> list[dict[str, str]]:
    """Validate that a category, when given, exists and is active."""
    if category_id is None:
        return []
    category = repo.get_category(session, category_id)
    if category is None or not category.is_active:
        return [_detail("category_id", "Category does not exist or is not active.")]
    return []


def _active_engineer(session: Session, assignee_id: uuid.UUID) -> User:
    """Load an assignee, or refuse one who is not an active Engineer.

    Raises:
        ValidationFailed: No such user, or not an active Engineer.
    """
    user = repo.get_user(session, assignee_id)
    if user is None or not user.is_active or user.role is not Role.ENGINEER:
        _raise_if([_detail("assignee_id", "Assignee must be an active Engineer.")])
    return user  # type: ignore[return-value]


def _raise_if(details: list[dict[str, str]]) -> None:
    if details:
        raise ValidationFailed("Request validation failed.", details=details)


# --------------------------------------------------------------------------- notifications


def _notify_admins_of_report(
    session: Session, principal: Principal, incident: Incident, at: dt.datetime
) -> None:
    """Tell every active Facility Admin that an incident was filed.

    An admin who files their own incident already knows, so they are skipped.
    """
    for admin_id in repo.active_admin_ids(session):
        if admin_id == principal.user_id:
            continue
        repo.add_notification(
            session,
            user_id=admin_id,
            incident=incident,
            kind=NotificationKind.REPORTED,
            actor_id=principal.user_id,
            at=at,
        )


def _notify_assignee(
    session: Session,
    principal: Principal,
    incident: Incident,
    previous_assignee_id: uuid.UUID | None,
    at: dt.datetime,
) -> None:
    """Tell the engineer an incident was just handed to.

    Only on an actual change of hands: re-saving the same assignee says
    nothing new. The assigner is always an admin and the assignee always an
    engineer, so nobody is ever told about their own act.
    """
    assignee_id = incident.assignee_id
    if assignee_id is None or assignee_id == previous_assignee_id:
        return
    repo.add_notification(
        session,
        user_id=assignee_id,
        incident=incident,
        kind=NotificationKind.ASSIGNED,
        actor_id=principal.user_id,
        at=at,
    )


_OUTCOME_KINDS = {
    IncidentStatus.RESOLVED: NotificationKind.RESOLVED,
    IncidentStatus.CLOSED: NotificationKind.CLOSED,
}


def _notify_reporter(
    session: Session,
    principal: Principal,
    incident: Incident,
    target: IncidentStatus,
    at: dt.datetime,
) -> None:
    """Tell the reporter their incident was resolved or closed.

    Only for the two outcomes a reporter waits on, and only when someone
    else took the step: a reporter who confirms and closes their own
    incident already knows.
    """
    kind = _OUTCOME_KINDS.get(target)
    if kind is None or incident.reporter_id == principal.user_id:
        return
    repo.add_notification(
        session,
        user_id=incident.reporter_id,
        incident=incident,
        kind=kind,
        actor_id=principal.user_id,
        at=at,
    )


def list_notifications(
    session: Session, principal: Principal, filters: NotificationFilters
) -> tuple[list[Notification], int, int]:
    """Page through the caller's notifications, with their unread total.

    Returns:
        The page, the total matching the filter, and the unread count over
        every notification the caller has (not only the page, not only the
        filter), which is what the badge shows.
    """
    rows, total = repo.list_notifications(session, principal, filters)
    return rows, total, repo.count_unread(session, principal)


def mark_notification_read(
    session: Session, principal: Principal, notification_id: uuid.UUID
) -> Notification:
    """Mark one of the caller's notifications read. Idempotent.

    Raises:
        NotFound: No such notification, or it belongs to someone else.
    """
    notification = repo.get_notification(session, principal, notification_id)
    if notification is None:
        raise NotFound("Notification not found.")
    if notification.read_at is None:
        notification.read_at = _now()
        session.flush()
    return notification


def mark_all_notifications_read(session: Session, principal: Principal) -> int:
    """Mark every unread notification the caller has as read.

    Returns:
        How many were unread.
    """
    rows = repo.unread_notifications(session, principal)
    now = _now()
    for row in rows:
        row.read_at = now
    session.flush()
    return len(rows)


# --------------------------------------------------------------------------- incidents


def create_incident(session: Session, principal: Principal, body: IncidentCreate) -> Incident:
    """Report an incident: Open, reported by the caller, with its first history row.

    Args:
        session: The request's session.
        principal: The reporter.
        body: The validated request.

    Returns:
        The new incident.

    Raises:
        ValidationFailed: A referenced building, floor, seat or category does
            not exist, is inactive, or does not nest as claimed.
    """
    details = _check_location(session, body.building_id, body.floor_id, body.seat_id)
    details += _check_category(session, body.category_id)
    _raise_if(details)

    incident = Incident(
        title=body.title,
        description=body.description,
        status=IncidentStatus.OPEN,
        priority=body.priority,
        category_id=body.category_id,
        building_id=body.building_id,
        floor_id=body.floor_id,
        seat_id=body.seat_id,
        reporter_id=principal.user_id,
    )
    session.add(incident)
    session.flush()
    now = _now()
    repo.add_history(session, incident, None, IncidentStatus.OPEN, principal.user_id, None, at=now)
    _notify_admins_of_report(session, principal, incident, now)
    session.flush()
    _logger.info("incident_created", extra={"incident_id": str(incident.id)})
    return incident


def list_incidents(
    session: Session, principal: Principal, filters: IncidentFilters
) -> tuple[list[Incident], int]:
    """Page through the incidents this caller may see."""
    return repo.list_incidents(session, principal, filters)


def get_incident(session: Session, principal: Principal, incident_id: uuid.UUID) -> Incident:
    """Fetch one visible incident.

    Raises:
        NotFound: No such incident, or not visible to this caller.
    """
    return _require(session, principal, incident_id)


def allowed_transitions(principal: Principal, incident: Incident) -> list[TransitionOption]:
    """The moves this caller may make on this incident right now.

    Each edge is judged as though the client will supply everything it
    requires, so `requires` tells the UI what to prompt for; a value the
    incident already holds (an assignee, say) is not asked for again.

    Args:
        principal: The caller.
        incident: The incident, as loaded.

    Returns:
        One option per permitted edge, in workflow order.
    """
    context = _context(principal, incident)
    options: list[TransitionOption] = []
    for rule in TRANSITIONS:
        if rule.source is not incident.status:
            continue
        needed = rule.required_payload | rule.required_state
        if not can_transition(context, rule.target, dict.fromkeys(needed, "provided")):
            continue
        requires = rule.required_payload | {
            field for field in rule.required_state if getattr(incident, field) is None
        }
        options.append(
            TransitionOption(to=rule.target, label=rule.label, requires=sorted(requires))
        )
    return options


def _editable_fields(principal: Principal, incident: Incident) -> frozenset[str]:
    """Which fields this caller may change on this incident through PUT."""
    if principal.is_admin:
        return _ADMIN_EDITABLE
    if incident.reporter_id == principal.user_id and incident.status is IncidentStatus.OPEN:
        return _REPORTER_EDITABLE_WHILE_OPEN
    return frozenset()


def update_incident(
    session: Session, principal: Principal, incident_id: uuid.UUID, body: IncidentUpdate
) -> Incident:
    """Edit an incident's details. Status is not among them.

    The whole request is judged before anything is applied: one field the
    caller may not change rejects all of them.

    Raises:
        NotFound: No such incident, or not visible.
        Conflict: The incident is Closed, or unassigning one that is not Open.
        Forbidden: The caller may see the incident but not change these fields.
        ValidationFailed: The category or assignee reference is unusable.
    """
    incident = _require(session, principal, incident_id, for_update=True)
    if incident.status is IncidentStatus.CLOSED:
        raise Conflict("A closed incident cannot be edited.")

    changes = body.changes()
    denied = sorted(set(changes) - _editable_fields(principal, incident))
    if denied:
        raise Forbidden(f"You may not change {', '.join(denied)} on this incident.")

    if changes.get("category_id") is not None:
        _raise_if(_check_category(session, changes["category_id"]))
    previous_assignee_id = incident.assignee_id
    if "assignee_id" in changes:
        if changes["assignee_id"] is None:
            if incident.status is not IncidentStatus.OPEN:
                raise Conflict("Only an Open incident can be unassigned.")
            incident.assignee = None
        else:
            # Through the relationship, so the response carries the summary
            # without a reload; the foreign key follows at flush.
            incident.assignee = _active_engineer(session, changes.pop("assignee_id"))

    for field, value in changes.items():
        setattr(incident, field, value)
    session.flush()
    now = _now()
    if incident.assignee_id is not None and incident.assignee_id != previous_assignee_id:
        # The status stays; the row records who handed it to whom, and when.
        repo.add_history(
            session,
            incident,
            incident.status,
            incident.status,
            principal.user_id,
            None,
            assignee_id=incident.assignee_id,
            at=now,
        )
    _notify_assignee(session, principal, incident, previous_assignee_id, now)
    session.flush()
    return incident


def delete_incident(session: Session, principal: Principal, incident_id: uuid.UUID) -> None:
    """Delete an incident and everything beneath it.

    The role gate has already run in the route; this only finds the row.

    Raises:
        NotFound: No such incident.
    """
    incident = _require(session, principal, incident_id, for_update=True)
    session.delete(incident)
    session.flush()
    _logger.info("incident_deleted", extra={"incident_id": str(incident_id)})


def transition(
    session: Session, principal: Principal, incident_id: uuid.UUID, body: TransitionRequest
) -> Incident:
    """Move an incident along one workflow edge.

    The checks run in the order api.md I6 pins, each with its own error, and
    the first failure wins: scope (404), edge (409), actor (403), required
    fields (400), then the assignee (403 for anyone but an admin naming one,
    400 for an assignee who is not an active Engineer).

    Raises:
        NotFound: No such incident, or not visible.
        InvalidTransition: No edge from the current status to the target.
        Forbidden: The edge exists but this caller may not take it, or the
            caller is not an admin and named an assignee.
        ValidationFailed: A required note is missing or blank, an assignee
            is needed and none exists, or the assignee is not an Engineer.
    """
    incident = _require(session, principal, incident_id, for_update=True)
    payload = body.model_dump(exclude_unset=True, exclude={"target_status"})
    validate_transition(_context(principal, incident), body.target_status, payload)
    previous_assignee_id = incident.assignee_id

    # Who this move hands the incident to, for the audit row. Read from the
    # payload: the relationship is set below, and the foreign key follows
    # only at flush.
    handed_to = None
    if body.assignee_id is not None:
        if not principal.is_admin:
            raise Forbidden("Only a Facility Admin may assign an incident.")
        incident.assignee = _active_engineer(session, body.assignee_id)
        if body.assignee_id != previous_assignee_id:
            handed_to = body.assignee_id

    now = _now()
    target = body.target_status
    if target is IncidentStatus.BLOCKED:
        incident.blocked_reason = body.blocked_reason
    elif incident.status is IncidentStatus.BLOCKED:
        # Leaving Blocked clears the reason; the history row written below
        # for the block itself still carries it.
        incident.blocked_reason = None
    if body.resolution_note is not None and body.resolution_note.strip():
        incident.resolution_note = body.resolution_note

    current = {field: getattr(incident, field) for field in _STAMP_FIELDS}
    for field, moment in stamps_for(target, current, now).items():
        setattr(incident, field, moment)

    note = body.resolution_note or body.blocked_reason
    repo.add_history(
        session,
        incident,
        incident.status,
        target,
        principal.user_id,
        note,
        assignee_id=handed_to,
        at=now,
    )
    incident.status = target
    session.flush()
    _notify_assignee(session, principal, incident, previous_assignee_id, now)
    _notify_reporter(session, principal, incident, target, now)
    session.flush()
    _logger.info(
        "incident_transitioned",
        extra={"incident_id": str(incident.id), "to_status": target.value},
    )
    return incident


# --------------------------------------------------------------------------- children


def list_history(
    session: Session, principal: Principal, incident_id: uuid.UUID, params: TimelineParams
) -> tuple[list[IncidentStatusHistory], int]:
    """Page through a visible incident's status changes.

    Raises:
        NotFound: No such incident, or not visible.
    """
    _require(session, principal, incident_id)
    return repo.list_history(session, principal, incident_id, params)


def list_notes(
    session: Session, principal: Principal, incident_id: uuid.UUID, params: TimelineParams
) -> tuple[list[IncidentNote], int]:
    """Page through a visible incident's notes, internal ones only for staff.

    Raises:
        NotFound: No such incident, or not visible.
    """
    _require(session, principal, incident_id)
    return repo.list_notes(session, principal, incident_id, params)


def create_note(
    session: Session, principal: Principal, incident_id: uuid.UUID, body: NoteCreate
) -> IncidentNote:
    """Add a note to a visible incident.

    Raises:
        NotFound: No such incident, or not visible.
        Conflict: The incident is Closed.
        Forbidden: A non-staff caller asked for an internal note. Refused
            rather than downgraded: publishing what the author meant to keep
            private is the worse failure.
    """
    incident = _require(session, principal, incident_id)
    if incident.status is IncidentStatus.CLOSED:
        raise Conflict("Notes cannot be added to a closed incident.")
    if body.visibility is NoteVisibility.INTERNAL and not principal.is_staff:
        raise Forbidden("Only staff may write internal notes.")
    # Stamped here, not by the column default: `now()` is the transaction
    # start in PostgreSQL, and a timeline needs rows written in one
    # transaction to keep their order.
    note = IncidentNote(
        incident_id=incident.id,
        author_id=principal.user_id,
        body=body.body,
        visibility=body.visibility,
        created_at=_now(),
    )
    session.add(note)
    session.flush()
    return note


# --------------------------------------------------------------------------- escalations


def list_incident_escalations(
    session: Session, principal: Principal, incident_id: uuid.UUID, params: TimelineParams
) -> tuple[list[EscalationRequest], int]:
    """Page through a visible incident's escalation requests.

    Raises:
        NotFound: No such incident, or not visible.
    """
    _require(session, principal, incident_id)
    return repo.list_incident_escalations(session, principal, incident_id, params)


def create_escalation(
    session: Session, principal: Principal, incident_id: uuid.UUID, body: EscalationCreate
) -> EscalationRequest:
    """Ask for an incident's priority to be raised.

    Raises:
        NotFound: No such incident, or not visible.
        Forbidden: The caller is neither the reporter nor the assigned engineer.
        Conflict: The incident is Resolved or Closed, already Critical, or
            already has a pending request.
    """
    incident = _require(session, principal, incident_id, for_update=True)
    is_reporter = incident.reporter_id == principal.user_id
    is_assigned = principal.role is Role.ENGINEER and incident.assignee_id == principal.user_id
    if not (is_reporter or is_assigned):
        raise Forbidden("Only the reporter or the assigned engineer may request an escalation.")
    if incident.status in (IncidentStatus.RESOLVED, IncidentStatus.CLOSED):
        raise Conflict(f"A {incident.status.value} incident cannot be escalated.")
    if incident.priority is Priority.CRITICAL:
        raise Conflict("The incident is already Critical.")
    if repo.has_pending_escalation(session, incident.id):
        raise Conflict("An escalation request is already pending for this incident.")

    escalation = EscalationRequest(
        incident_id=incident.id,
        requested_by_id=principal.user_id,
        reason=body.reason,
        created_at=_now(),  # the queue is ordered by this; see create_note
    )
    session.add(escalation)
    session.flush()
    return escalation


def list_escalations(
    session: Session, principal: Principal, filters: EscalationFilters
) -> tuple[list[EscalationRequest], int]:
    """Page through the escalation queue."""
    return repo.list_escalations(session, principal, filters)


def decide_escalation(
    session: Session, principal: Principal, escalation_id: uuid.UUID, body: EscalationDecision
) -> EscalationRequest:
    """Approve or reject a pending escalation.

    Approval raises the incident's priority one level in the same transaction.

    Raises:
        NotFound: No such escalation, or its incident is not visible.
        Conflict: The escalation was already decided.
    """
    escalation = repo.get_escalation_for_update(session, principal, escalation_id)
    if escalation is None:
        raise NotFound("Escalation not found.")
    if escalation.status is not EscalationStatus.PENDING:
        raise Conflict(f"This escalation was already {escalation.status.value.lower()}.")

    escalation.status = body.decision
    # Through the relationship, so the response carries the summary without
    # a reload. The caller's row is already in the identity map.
    escalation.decided_by = repo.get_user(session, principal.user_id)
    escalation.decided_at = _now()
    escalation.decision_note = body.decision_note
    if body.decision is EscalationStatus.APPROVED:
        incident = escalation.incident
        incident.priority = _NEXT_PRIORITY.get(incident.priority, incident.priority)
    session.flush()
    return escalation


# --------------------------------------------------------------------------- reports


def _buckets(counts: Mapping[Any, int], keys: list[Any]) -> list[CountBucket]:
    """Zero-filled counts in a fixed order, so a chart's axes never shift."""
    return [
        CountBucket(key=getattr(key, "value", key), count=counts.get(key, 0)) for key in keys
    ]


def summary_report(session: Session, window: ReportRange) -> SummaryReport:
    """Counts by status and priority, and the age of the open backlog."""
    by_status = repo.count_by(session, window, Incident.status)
    by_priority = repo.count_by(session, window, Incident.priority)
    backlog = repo.backlog_by_age(session, window, _now())
    return SummaryReport(
        date_from=window.date_from,
        date_to=window.date_to,
        total=sum(by_status.values()),
        by_status=_buckets(by_status, list(IncidentStatus)),
        by_priority=_buckets(by_priority, list(Priority)),
        backlog_by_age=_buckets(backlog, [label for label, _ in repo.AGE_BUCKETS]),
    )


def _label(value: Any) -> str:
    return str(getattr(value, "value", value))


def _seconds(value: Any) -> float | None:
    return None if value is None else float(value)


def sla_report(session: Session, params: SlaParams) -> SlaReport:
    """Time-to-acknowledge and time-to-resolve per group, against the targets."""
    rows = [
        SlaRow(
            group=_label(group),
            count=count,
            resolved_count=resolved,
            mean_ack_seconds=_seconds(mean_ack),
            p90_ack_seconds=_seconds(p90_ack),
            mean_resolve_seconds=_seconds(mean_resolve),
            p90_resolve_seconds=_seconds(p90_resolve),
            within_target_ratio=(int(within) / resolved) if resolved else None,
        )
        for group, count, resolved, mean_ack, p90_ack, mean_resolve, p90_resolve, within in (
            repo.sla_rows(session, params)
        )
    ]
    return SlaReport(
        date_from=params.date_from,
        date_to=params.date_to,
        group_by=params.group_by,
        targets=[
            SlaTarget(priority=priority, target_seconds=int(delta.total_seconds()))
            for priority, delta in SLA_TARGETS.items()
        ],
        rows=rows,
    )


def volume_report(session: Session, params: VolumeParams) -> VolumeReport:
    """Incidents created per interval bucket per group."""
    return VolumeReport(
        date_from=params.date_from,
        date_to=params.date_to,
        interval=params.interval,
        group_by=params.group_by,
        rows=[
            VolumeRow(bucket_start=bucket.date(), group=_label(group), count=count)
            for bucket, group, count in repo.volume_rows(session, params)
        ],
    )


def buildings_report(session: Session, window: ReportRange) -> BuildingsReport:
    """Incident counts per building, busiest first."""
    return BuildingsReport(
        date_from=window.date_from,
        date_to=window.date_to,
        rows=[
            BuildingRow(
                building_id=building_id,
                building=name,
                count=count,
                open_count=int(open_count),
                critical_count=int(critical),
            )
            for building_id, name, _active, count, open_count, critical in (
                repo.building_rows(session, window)
            )
        ],
    )


def engineers_report(session: Session, window: ReportRange) -> EngineersReport:
    """Workload and throughput per engineer, most completed first."""
    return EngineersReport(
        date_from=window.date_from,
        date_to=window.date_to,
        rows=[
            EngineerRow(
                engineer_id=engineer_id,
                engineer=name,
                specialty=specialty,
                is_active=is_active,
                assigned_count=assigned,
                open_count=int(open_count),
                completed_count=int(completed),
                mean_resolve_seconds=_seconds(mean_resolve),
            )
            for (
                engineer_id,
                name,
                specialty,
                is_active,
                assigned,
                open_count,
                completed,
                mean_resolve,
            ) in repo.engineer_rows(session, window)
        ],
    )
