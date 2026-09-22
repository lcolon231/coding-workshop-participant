"""HTTP routes for the incidents service, mounted under /api/incidents.

Every handler is a plain `def`: SQLAlchemy is synchronous, and a sync call
inside `async def` would block the event loop for every other request (A6).

Registration order is part of the contract (api.md §4): `/workflow`,
`/escalations` and `/reports/*` are added **before** any `/{incident_id}`
route, or the typed UUID parameter turns them into a confusing `400`.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Query, Response, status

from acme_core.dependencies import AdminPrincipal, CurrentPrincipal, DbSession
from acme_core.errors import error_responses
from acme_core.schemas.common import Page, TimelineParams
from acme_core.schemas.incident import (
    EscalationCreate,
    EscalationDecision,
    EscalationFilters,
    EscalationOut,
    IncidentCreate,
    IncidentDetailOut,
    IncidentFilters,
    IncidentOut,
    IncidentUpdate,
    NoteCreate,
    NoteOut,
    StatusHistoryOut,
    TransitionRequest,
    WorkflowOut,
)
from acme_core.schemas.report import (
    ReportRange,
    SlaParams,
    SlaReport,
    SummaryReport,
    VolumeParams,
    VolumeReport,
)
from acme_core.workflow import describe
from incidents_service import service

router = APIRouter()

PREFIX = "/api/incidents"

Timeline = Annotated[TimelineParams, Query()]


def _page(model: Any, rows: list[Any], total: int, params: TimelineParams) -> Page[Any]:
    """Shape one page of ORM rows as the response envelope."""
    return Page[model](
        items=[model.model_validate(row) for row in rows],
        total=total,
        limit=params.limit,
        offset=params.offset,
    )


# --------------------------------------------------------------------------- static paths first


@router.get(
    "/workflow",
    response_model=WorkflowOut,
    responses=error_responses(401),
    tags=["workflow"],
    summary="The whole state machine",
)
def workflow(_caller: CurrentPrincipal) -> WorkflowOut:
    """Every status and every edge, with who may take it and what it requires.

    Static per deploy; a client may cache it for the session. The per-incident
    answer is `allowed_transitions` on a single incident.
    """
    return WorkflowOut.model_validate(describe())


@router.get(
    "/escalations",
    response_model=Page[EscalationOut],
    responses=error_responses(400, 401, 403),
    tags=["escalations"],
    summary="The escalation queue",
)
def list_escalations(
    admin: AdminPrincipal, session: DbSession, filters: Annotated[EscalationFilters, Query()]
) -> Page[EscalationOut]:
    """Every escalation request, pending ones by default, oldest first."""
    rows, total = service.list_escalations(session, admin, filters)
    return _page(EscalationOut, rows, total, filters)


@router.post(
    "/escalations/{escalation_id}/decision",
    response_model=EscalationOut,
    responses=error_responses(400, 401, 403, 404, 409),
    tags=["escalations"],
    summary="Decide an escalation",
)
def decide_escalation(
    escalation_id: uuid.UUID, body: EscalationDecision, admin: AdminPrincipal, session: DbSession
) -> EscalationOut:
    """Approve or reject. Approval raises the incident's priority one level."""
    return EscalationOut.model_validate(
        service.decide_escalation(session, admin, escalation_id, body)
    )


@router.get(
    "/reports/summary",
    response_model=SummaryReport,
    responses=error_responses(400, 401, 403),
    tags=["reports"],
    summary="Counts and backlog age",
)
def report_summary(
    admin: AdminPrincipal, session: DbSession, window: Annotated[ReportRange, Query()]
) -> SummaryReport:
    """Incidents created in the window by status and priority, and the open backlog by age."""
    del admin
    return service.summary_report(session, window)


@router.get(
    "/reports/sla",
    response_model=SlaReport,
    responses=error_responses(400, 401, 403),
    tags=["reports"],
    summary="Time to acknowledge and resolve",
)
def report_sla(
    admin: AdminPrincipal, session: DbSession, params: Annotated[SlaParams, Query()]
) -> SlaReport:
    """Mean and p90 durations per group, and the share resolved within target."""
    del admin
    return service.sla_report(session, params)


@router.get(
    "/reports/volume",
    response_model=VolumeReport,
    responses=error_responses(400, 401, 403),
    tags=["reports"],
    summary="Incidents created per interval",
)
def report_volume(
    admin: AdminPrincipal, session: DbSession, params: Annotated[VolumeParams, Query()]
) -> VolumeReport:
    """Incidents created per day or week, split by status, priority or category."""
    del admin
    return service.volume_report(session, params)


# --------------------------------------------------------------------------- the collection


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=IncidentOut,
    responses=error_responses(400, 401),
    tags=["incidents"],
    summary="Report an incident",
)
def create_incident(
    body: IncidentCreate, caller: CurrentPrincipal, session: DbSession, response: Response
) -> IncidentOut:
    """Open a new incident. The reporter is the caller; the status is always Open."""
    incident = service.create_incident(session, caller, body)
    response.headers["Location"] = f"{PREFIX}/{incident.id}"
    return IncidentOut.model_validate(incident)


@router.get(
    "",
    response_model=Page[IncidentOut],
    responses=error_responses(400, 401),
    tags=["incidents"],
    summary="List incidents",
)
def list_incidents(
    caller: CurrentPrincipal, session: DbSession, filters: Annotated[IncidentFilters, Query()]
) -> Page[IncidentOut]:
    """Page through the incidents the caller may see; every filter applies inside that scope."""
    rows, total = service.list_incidents(session, caller, filters)
    return _page(IncidentOut, rows, total, filters)


# --------------------------------------------------------------------------- one incident


@router.get(
    "/{incident_id}",
    response_model=IncidentDetailOut,
    responses=error_responses(400, 401, 404),
    tags=["incidents"],
    summary="Get an incident",
)
def get_incident(
    incident_id: uuid.UUID, caller: CurrentPrincipal, session: DbSession
) -> IncidentDetailOut:
    """One incident, with the transitions this caller may make on it right now."""
    incident = service.get_incident(session, caller, incident_id)
    return IncidentDetailOut(
        **IncidentOut.model_validate(incident).model_dump(),
        allowed_transitions=service.allowed_transitions(caller, incident),
    )


@router.put(
    "/{incident_id}",
    response_model=IncidentOut,
    responses=error_responses(400, 401, 403, 404, 409),
    tags=["incidents"],
    summary="Edit an incident",
)
def update_incident(
    incident_id: uuid.UUID, body: IncidentUpdate, caller: CurrentPrincipal, session: DbSession
) -> IncidentOut:
    """Partial update of the details. Status changes only through the transition endpoint."""
    return IncidentOut.model_validate(service.update_incident(session, caller, incident_id, body))


@router.delete(
    "/{incident_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=error_responses(400, 401, 403, 404),
    tags=["incidents"],
    summary="Delete an incident",
)
def delete_incident(incident_id: uuid.UUID, admin: AdminPrincipal, session: DbSession) -> Response:
    """Remove an incident with its notes, history and escalations. Admin only."""
    service.delete_incident(session, admin, incident_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{incident_id}/transition",
    response_model=IncidentOut,
    responses=error_responses(400, 401, 403, 404, 409),
    tags=["workflow"],
    summary="Move an incident to another status",
)
def transition(
    incident_id: uuid.UUID, body: TransitionRequest, caller: CurrentPrincipal, session: DbSession
) -> IncidentOut:
    """The only way status changes. The workflow decides the edge, the actor and the fields."""
    return IncidentOut.model_validate(service.transition(session, caller, incident_id, body))


@router.get(
    "/{incident_id}/history",
    response_model=Page[StatusHistoryOut],
    responses=error_responses(400, 401, 404),
    tags=["workflow"],
    summary="Status history",
)
def list_history(
    incident_id: uuid.UUID, caller: CurrentPrincipal, session: DbSession, params: Timeline
) -> Page[StatusHistoryOut]:
    """Every status change, oldest first. Append-only; there is no write endpoint."""
    rows, total = service.list_history(session, caller, incident_id, params)
    return _page(StatusHistoryOut, rows, total, params)


@router.get(
    "/{incident_id}/notes",
    response_model=Page[NoteOut],
    responses=error_responses(400, 401, 404),
    tags=["notes"],
    summary="List notes",
)
def list_notes(
    incident_id: uuid.UUID, caller: CurrentPrincipal, session: DbSession, params: Timeline
) -> Page[NoteOut]:
    """Notes oldest first. Internal notes are shown to staff only."""
    rows, total = service.list_notes(session, caller, incident_id, params)
    return _page(NoteOut, rows, total, params)


@router.post(
    "/{incident_id}/notes",
    status_code=status.HTTP_201_CREATED,
    response_model=NoteOut,
    responses=error_responses(400, 401, 403, 404, 409),
    tags=["notes"],
    summary="Add a note",
)
def create_note(
    incident_id: uuid.UUID,
    body: NoteCreate,
    caller: CurrentPrincipal,
    session: DbSession,
    response: Response,
) -> NoteOut:
    """Append a note. Notes are never edited or deleted; they are part of the audit trail."""
    note = service.create_note(session, caller, incident_id, body)
    response.headers["Location"] = f"{PREFIX}/{incident_id}/notes"
    return NoteOut.model_validate(note)


@router.get(
    "/{incident_id}/escalations",
    response_model=Page[EscalationOut],
    responses=error_responses(400, 401, 404),
    tags=["escalations"],
    summary="List an incident's escalations",
)
def list_incident_escalations(
    incident_id: uuid.UUID, caller: CurrentPrincipal, session: DbSession, params: Timeline
) -> Page[EscalationOut]:
    """Escalation requests on one incident, oldest first."""
    rows, total = service.list_incident_escalations(session, caller, incident_id, params)
    return _page(EscalationOut, rows, total, params)


@router.post(
    "/{incident_id}/escalations",
    status_code=status.HTTP_201_CREATED,
    response_model=EscalationOut,
    responses=error_responses(400, 401, 403, 404, 409),
    tags=["escalations"],
    summary="Request an escalation",
)
def create_escalation(
    incident_id: uuid.UUID,
    body: EscalationCreate,
    caller: CurrentPrincipal,
    session: DbSession,
    response: Response,
) -> EscalationOut:
    """Ask an admin to raise the priority. Reporter or assigned engineer only, one at a time."""
    escalation = service.create_escalation(session, caller, incident_id, body)
    response.headers["Location"] = f"{PREFIX}/{incident_id}/escalations"
    return EscalationOut.model_validate(escalation)
