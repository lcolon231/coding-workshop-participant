"""Request and response bodies for incidents."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Annotated, ClassVar

from pydantic import ConfigDict, Field, field_validator, model_validator

from acme_core.models.enums import EscalationStatus, IncidentStatus, NoteVisibility, Priority
from acme_core.schemas.auth import UserSummary
from acme_core.schemas.common import (
    Order,
    PageParams,
    ResponseModel,
    StrictModel,
    UpdateModel,
)
from acme_core.workflow import Actor

Title = Annotated[str, Field(min_length=1, max_length=200)]
Body = Annotated[str, Field(min_length=1)]
LongNote = Annotated[str, Field(max_length=4000)]


class IncidentCreate(StrictModel):
    """Report an incident.

    Contains no `reporter_id` and no `status`. The reporter comes from the
    authenticated principal, and the status is whatever the workflow says it
    is -- accepting either from a client would let one employee file an
    incident as another, or skip the state machine entirely.
    """

    title: Title
    description: Body
    # The reporter's own view of urgency. Only an admin may change it later.
    priority: Priority = Priority.MEDIUM
    category_id: uuid.UUID | None = None
    # Required: every incident happens somewhere.
    building_id: uuid.UUID
    # Optional: a lobby has no seat, a lift has no floor.
    floor_id: uuid.UUID | None = None
    seat_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def _seat_needs_a_floor(self) -> IncidentCreate:
        """A seat without a floor is incoherent, and would break the UI cascade."""
        if self.seat_id is not None and self.floor_id is None:
            raise ValueError("floor_id is required when seat_id is given")
        return self


class IncidentUpdate(UpdateModel):
    """Edit an incident's details.

    Status is absent on purpose: it moves only through
    POST /api/incidents/{id}/transition, which applies the workflow rules.
    A generic PUT that accepted `status` would bypass them entirely.

    Which caller may change which field -- the reporter edits the text while
    the incident is Open, only an admin touches priority or assignee -- depends
    on the row, so the service enforces it. `null` unassigns or uncategorises.
    """

    CLEARABLE: ClassVar[frozenset[str]] = frozenset({"category_id", "assignee_id"})

    title: Title | None = None
    description: Body | None = None
    priority: Priority | None = None
    category_id: uuid.UUID | None = None
    assignee_id: uuid.UUID | None = None


class TransitionRequest(StrictModel):
    """Move an incident to another status.

    The extra fields are the ones the workflow may require; which are needed
    depends on the edge, and the client learns that from GET /api/incidents/workflow.
    """

    target_status: IncidentStatus
    assignee_id: uuid.UUID | None = None
    resolution_note: LongNote | None = None
    blocked_reason: LongNote | None = None


class IncidentFilters(PageParams):
    """Query parameters for the incident list."""

    status: IncidentStatus | None = None
    priority: Priority | None = None
    building_id: uuid.UUID | None = None
    category_id: uuid.UUID | None = None
    assignee_id: uuid.UUID | None = None
    search: Annotated[str | None, Field(max_length=200)] = None
    # Inclusive dates on `created_at`, so the dashboard can list exactly the
    # incidents its reports counted (the same window rule as `ReportRange`).
    created_from: dt.date | None = None
    created_to: dt.date | None = None
    # A literal allowlist, never a raw column name. Interpolating a client
    # string into ORDER BY is injectable, and getattr(Model, value) allows
    # traversal onto relationships and dunder attributes.
    sort: Annotated[str, Field(pattern="^(created_at|priority|status|title)$")] = "created_at"
    order: Order = "desc"

    @model_validator(mode="after")
    def _dates_in_order(self) -> IncidentFilters:
        if (
            self.created_from is not None
            and self.created_to is not None
            and self.created_from > self.created_to
        ):
            raise ValueError("created_from must not be after created_to")
        return self


class NoteCreate(StrictModel):
    """Add a note to an incident."""

    body: Annotated[str, Field(min_length=1, max_length=4000)]
    # An employee asking for "internal" is refused by the service, not
    # downgraded: publishing what the author meant to keep private is worse.
    visibility: NoteVisibility = NoteVisibility.PUBLIC


class NoteOut(ResponseModel):
    """A note."""

    id: uuid.UUID
    incident_id: uuid.UUID
    author_id: uuid.UUID
    author: UserSummary
    body: str
    visibility: NoteVisibility
    created_at: dt.datetime


class StatusHistoryOut(ResponseModel):
    """One recorded status change or assignment.

    `assignee` is the engineer this event handed the incident to, or null
    when it changed no hands. A plain assignment (edit, no status change)
    has `from_status == to_status`.
    """

    id: uuid.UUID
    from_status: IncidentStatus | None
    to_status: IncidentStatus
    actor_id: uuid.UUID
    actor: UserSummary
    assignee_id: uuid.UUID | None
    assignee: UserSummary | None
    note: str | None
    created_at: dt.datetime


class IncidentOut(ResponseModel):
    """An incident."""

    id: uuid.UUID
    title: str
    description: str
    status: IncidentStatus
    priority: Priority
    # The ids stay alongside the summaries so a client can compare against
    # its own id without reaching into a nested object.
    reporter_id: uuid.UUID
    reporter: UserSummary
    assignee_id: uuid.UUID | None
    assignee: UserSummary | None
    category_id: uuid.UUID | None
    building_id: uuid.UUID
    floor_id: uuid.UUID | None
    seat_id: uuid.UUID | None
    acknowledged_at: dt.datetime | None
    assigned_at: dt.datetime | None
    resolved_at: dt.datetime | None
    closed_at: dt.datetime | None
    resolution_note: str | None
    blocked_reason: str | None
    created_at: dt.datetime
    updated_at: dt.datetime


class TransitionOption(ResponseModel):
    """One action this caller may take on this incident right now."""

    to: IncidentStatus
    label: str
    requires: list[str] = Field(description="Fields the request must supply, non-blank.")


class IncidentDetailOut(IncidentOut):
    """A single incident, with the actions available to the caller.

    `allowed_transitions` comes from `workflow.allowed_targets`, the same code
    the transition endpoint validates with, so the UI cannot offer a button the
    API will refuse.
    """

    allowed_transitions: list[TransitionOption]


class WorkflowTransitionOut(ResponseModel):
    """One edge of the state machine, as `workflow.describe()` emits it."""

    # `from` is a Python keyword, so the attribute is `source` and the wire
    # name is `from`, in both directions.
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    source: IncidentStatus = Field(alias="from")
    to: IncidentStatus
    label: str
    allowed_actors: list[Actor]
    requires: list[str]


class WorkflowOut(ResponseModel):
    """The whole state machine, served at `GET /api/incidents/workflow`."""

    statuses: list[IncidentStatus]
    transitions: list[WorkflowTransitionOut]


class EscalationCreate(StrictModel):
    """Ask for an incident's priority to be raised."""

    reason: Annotated[str, Field(min_length=1, max_length=4000)]


class EscalationDecision(StrictModel):
    """An admin's verdict on a pending escalation.

    The field is `decision`, not `status`: `status` is server-controlled, and a
    request schema carrying it would (rightly) fail the mass-assignment test.
    """

    decision: EscalationStatus
    decision_note: LongNote | None = None

    @field_validator("decision")
    @classmethod
    def _must_be_a_verdict(cls, value: EscalationStatus) -> EscalationStatus:
        """Pending is where an escalation starts, not a decision about it."""
        if value is EscalationStatus.PENDING:
            raise ValueError("must be Approved or Rejected")
        return value


class EscalationFilters(PageParams):
    """Query parameters for the admin escalation queue: oldest pending first."""

    status: EscalationStatus | None = EscalationStatus.PENDING
    order: Order = "asc"


class EscalationOut(ResponseModel):
    """An escalation request and, once made, its decision."""

    id: uuid.UUID
    incident_id: uuid.UUID
    requested_by: UserSummary
    reason: str
    status: EscalationStatus
    decided_by: UserSummary | None
    decided_at: dt.datetime | None
    decision_note: str | None
    created_at: dt.datetime
