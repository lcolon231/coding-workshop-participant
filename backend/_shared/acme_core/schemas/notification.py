"""Response bodies and query parameters for in-app notifications."""

from __future__ import annotations

import datetime as dt
import uuid

from acme_core.models.enums import NotificationKind
from acme_core.schemas.auth import UserSummary
from acme_core.schemas.common import Page, PageParams, ResponseModel


class NotificationFilters(PageParams):
    """Query parameters for one user's notifications, newest first."""

    # True lists only what is still unread; omitted lists everything.
    unread: bool | None = None


class NotificationOut(ResponseModel):
    """Something the caller was told about an incident.

    Carries the kind and the facts rather than a sentence, so the client
    phrases it and a wording change needs no migration.
    """

    id: uuid.UUID
    kind: NotificationKind
    incident_id: uuid.UUID
    incident_title: str
    actor: UserSummary | None
    read_at: dt.datetime | None
    created_at: dt.datetime


class NotificationPage(Page[NotificationOut]):
    """A page of notifications plus the unread total, for the badge.

    One round trip serves both the badge and the list: the count is over
    every unread row the caller has, not only the page shown.
    """

    unread_count: int
