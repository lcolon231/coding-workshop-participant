"""Request and response bodies for incidents."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Annotated

from pydantic import Field, model_validator

from acme_core.models.enums import IncidentStatus, NoteVisibility, Priority
from acme_core.schemas.common import PageParams, ResponseModel, StrictModel


class IncidentCreate(StrictModel):
    """Report an incident.

    Contains no `reporter_id` and no `status`. The reporter comes from the
    authenticated principal, and the status is whatever the workflow says it
    is -- accepting either from a client would let one employee file an
    incident as another, or skip the state machine entirely.
    """

    title: Annotated[str, Field(min_length=1, max_length=200)]
    description: Annotated[str, Field(min_length=1)]
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


class IncidentUpdate(StrictModel):
    """Edit an incident's details.

    Status is absent on purpose: it moves only through
    POST /api/incidents/{id}/transition, which applies the workflow rules.
    A generic PUT that accepted `status` would bypass them entirely.
    """

    title: Annotated[str | None, Field(min_length=1, max_length=200)] = None
    description: Annotated[str | None, Field(min_length=1)] = None
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
    resolution_note: Annotated[str | None, Field(max_length=4000)] = None
    blocked_reason: Annotated[str | None, Field(max_length=4000)] = None


class IncidentFilters(PageParams):
    """Query parameters for the incident list."""

    status: IncidentStatus | None = None
    priority: Priority | None = None
    building_id: uuid.UUID | None = None
    assignee_id: uuid.UUID | None = None
    search: Annotated[str | None, Field(max_length=200)] = None
    # A literal allowlist, never a raw column name. Interpolating a client
    # string into ORDER BY is injectable, and getattr(Model, value) allows
    # traversal onto relationships and dunder attributes.
    sort: Annotated[str, Field(pattern="^(created_at|priority|status|title)$")] = "created_at"
    order: Annotated[str, Field(pattern="^(asc|desc)$")] = "desc"


class NoteCreate(StrictModel):
    """Add a note to an incident."""

    body: Annotated[str, Field(min_length=1, max_length=4000)]
    visibility: NoteVisibility = NoteVisibility.PUBLIC


class NoteOut(ResponseModel):
    """A note."""

    id: uuid.UUID
    incident_id: uuid.UUID
    author_id: uuid.UUID
    body: str
    visibility: NoteVisibility
    created_at: dt.datetime


class StatusHistoryOut(ResponseModel):
    """One recorded status change."""

    id: uuid.UUID
    from_status: IncidentStatus | None
    to_status: IncidentStatus
    actor_id: uuid.UUID
    note: str | None
    created_at: dt.datetime


class IncidentOut(ResponseModel):
    """An incident."""

    id: uuid.UUID
    title: str
    description: str
    status: IncidentStatus
    priority: Priority
    reporter_id: uuid.UUID
    assignee_id: uuid.UUID | None
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
