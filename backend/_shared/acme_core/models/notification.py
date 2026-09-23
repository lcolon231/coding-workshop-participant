"""In-app notifications: one row per person per thing they should know about."""

import datetime as dt
import uuid
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from acme_core.db.base import Base, UUIDPrimaryKeyMixin
from acme_core.models.enums import NotificationKind
from acme_core.models.types import enum_type
from acme_core.models.user import User


class Notification(UUIDPrimaryKeyMixin, Base):
    """Something one user should be told about one incident.

    Written in the same transaction as the action that caused it (a report,
    an assignment), so a notification can never describe a change that was
    rolled back, and a change can never be committed without its notification.

    The recipient is the only reader: every query filters on `user_id`, so a
    row belonging to someone else is invisible rather than forbidden, the same
    404-not-403 rule incidents follow.
    """

    __tablename__ = "notifications"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    incident_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("incidents.id", ondelete="CASCADE"), nullable=False
    )
    # Who did the thing being announced. SET NULL rather than RESTRICT: the
    # announcement still reads without a name.
    actor_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    kind: Mapped[NotificationKind] = mapped_column(enum_type(NotificationKind), nullable=False)
    # A snapshot, so the notification still says what it said even after the
    # title is edited, and so listing needs no join to `incidents`.
    incident_title: Mapped[str] = mapped_column(String(200), nullable=False)
    read_at: Mapped[Optional[dt.datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    actor: Mapped[Optional["User"]] = relationship(foreign_keys=[actor_id])

    __table_args__ = (
        # The only read: one user's rows, newest first, and their unread count.
        Index("ix_notifications_user_id_created_at", "user_id", "created_at"),
        Index("ix_notifications_incident_id", "incident_id"),
    )

    def __repr__(self) -> str:
        """Return a short representation."""
        return f"<Notification user={self.user_id} kind={self.kind!r} read={bool(self.read_at)}>"
