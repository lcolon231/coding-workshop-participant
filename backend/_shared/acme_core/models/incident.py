"""Incidents and the records that hang off them."""

import datetime as dt
import uuid
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from acme_core.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from acme_core.models.enums import (
    EscalationStatus,
    IncidentStatus,
    NoteVisibility,
    Priority,
)
from acme_core.models.types import enum_type
from acme_core.models.user import User


class Incident(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A reported problem with a facility or workplace technology."""

    __tablename__ = "incidents"

    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[IncidentStatus] = mapped_column(
        enum_type(IncidentStatus), nullable=False, default=IncidentStatus.OPEN
    )
    priority: Mapped[Priority] = mapped_column(
        enum_type(Priority), nullable=False, default=Priority.MEDIUM
    )

    reporter_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    assignee_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    category_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("categories.id", ondelete="RESTRICT"), nullable=True
    )

    # Building is required; floor and seat are not. Every incident happens
    # somewhere, but a lobby or a lift has no floor or seat to name.
    building_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("buildings.id", ondelete="RESTRICT"), nullable=False
    )
    floor_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("floors.id", ondelete="SET NULL"), nullable=True
    )
    seat_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("seats.id", ondelete="SET NULL"), nullable=True
    )

    # Stamped lifecycle timestamps, carried alongside incident_status_history.
    # Denormalised on purpose: SLA reporting becomes a GROUP BY over these
    # columns rather than a window function over the history table.
    #
    # acknowledged_at and assigned_at record the FIRST occurrence; resolved_at
    # and closed_at record the LATEST. A reopened ticket that kept its first
    # resolved_at would report a time-to-resolve that silently excludes all the
    # work done after the reopen. The policy lives in acme_core.workflow.
    acknowledged_at: Mapped[Optional[dt.datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    assigned_at: Mapped[Optional[dt.datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    resolved_at: Mapped[Optional[dt.datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    closed_at: Mapped[Optional[dt.datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    resolution_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    blocked_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    reporter: Mapped["User"] = relationship(
        back_populates="reported_incidents", foreign_keys=[reporter_id]
    )
    assignee: Mapped[Optional["User"]] = relationship(
        back_populates="assigned_incidents", foreign_keys=[assignee_id]
    )
    notes: Mapped[list["IncidentNote"]] = relationship(
        back_populates="incident", cascade="all, delete-orphan"
    )
    status_history: Mapped[list["IncidentStatusHistory"]] = relationship(
        back_populates="incident", cascade="all, delete-orphan"
    )
    escalations: Mapped[list["EscalationRequest"]] = relationship(
        back_populates="incident", cascade="all, delete-orphan"
    )

    __table_args__ = (
        # Row-level scoping filters on these two on every single list query.
        Index("ix_incidents_reporter_id", "reporter_id"),
        Index("ix_incidents_assignee_id", "assignee_id"),
        # The default list view is "open work, newest first".
        Index("ix_incidents_status_created_at", "status", "created_at"),
        Index("ix_incidents_building_id", "building_id"),
    )

    def __repr__(self) -> str:
        """Return a short representation."""
        return f"<Incident {self.title!r} status={self.status!r}>"


class IncidentNote(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A comment on an incident.

    Internal notes are visible to Facility Admins and Engineers only. That
    filter is applied by `acme_core.scoping.scope_notes`, never by a route
    handler deciding for itself.
    """

    __tablename__ = "incident_notes"

    incident_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("incidents.id", ondelete="CASCADE"), nullable=False
    )
    author_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    visibility: Mapped[NoteVisibility] = mapped_column(
        enum_type(NoteVisibility), nullable=False, default=NoteVisibility.PUBLIC
    )

    incident: Mapped["Incident"] = relationship(back_populates="notes")

    __table_args__ = (Index("ix_incident_notes_incident_id", "incident_id"),)

    def __repr__(self) -> str:
        """Return a short representation."""
        return f"<IncidentNote incident={self.incident_id} visibility={self.visibility!r}>"


class IncidentStatusHistory(UUIDPrimaryKeyMixin, Base):
    """An append-only record of one status change.

    The audit trail. The stamped columns on `incidents` are a denormalised
    convenience for reporting; this table is the source of truth for what
    happened, when, and who did it.
    """

    __tablename__ = "incident_status_history"

    incident_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("incidents.id", ondelete="CASCADE"), nullable=False
    )
    # Null for the row recording creation, which has no prior status.
    # Distinct type names: both columns are IncidentStatus, and the CHECK is
    # named after the type, so sharing one name collides within this table.
    from_status: Mapped[Optional[IncidentStatus]] = mapped_column(
        enum_type(IncidentStatus, name="history_from_status"), nullable=True
    )
    to_status: Mapped[IncidentStatus] = mapped_column(
        enum_type(IncidentStatus, name="history_to_status"), nullable=False
    )
    actor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    incident: Mapped["Incident"] = relationship(back_populates="status_history")

    __table_args__ = (
        Index("ix_incident_status_history_incident_id", "incident_id", "created_at"),
    )

    def __repr__(self) -> str:
        """Return a short representation."""
        return f"<StatusHistory {self.from_status!r} -> {self.to_status!r}>"


class EscalationRequest(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A request to raise an incident's urgency, and its decision."""

    __tablename__ = "escalation_requests"

    incident_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("incidents.id", ondelete="CASCADE"), nullable=False
    )
    requested_by_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[EscalationStatus] = mapped_column(
        enum_type(EscalationStatus), nullable=False, default=EscalationStatus.PENDING
    )
    decided_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    decided_at: Mapped[Optional[dt.datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    decision_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    incident: Mapped["Incident"] = relationship(back_populates="escalations")

    __table_args__ = (Index("ix_escalation_requests_incident_id", "incident_id"),)

    def __repr__(self) -> str:
        """Return a short representation."""
        return f"<EscalationRequest incident={self.incident_id} status={self.status!r}>"
