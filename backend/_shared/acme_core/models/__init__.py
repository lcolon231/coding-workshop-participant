"""Every ORM model, imported so `Base.metadata` is complete.

Alembic autogenerate compares `Base.metadata` against the live database. A
model module that nothing imports is invisible to that comparison, so the
migration silently omits its table. Importing them all here makes
`import acme_core.models` sufficient, and the re-exports below keep callers
from reaching into individual modules.
"""

from acme_core.db.base import Base
from acme_core.models.catalog import Category
from acme_core.models.enums import (
    EscalationStatus,
    IncidentStatus,
    NotificationKind,
    NoteVisibility,
    Priority,
    Role,
)
from acme_core.models.facility import Building, Floor, Seat
from acme_core.models.incident import (
    EscalationRequest,
    Incident,
    IncidentNote,
    IncidentStatusHistory,
)
from acme_core.models.notification import Notification
from acme_core.models.user import AppSecret, EngineerProfile, RefreshToken, User

# The complete set, asserted against Base.metadata by the test suite so a new
# model cannot be added without appearing here -- and therefore in migrations.
EXPECTED_TABLES = frozenset(
    {
        "app_secrets",
        "buildings",
        "categories",
        "engineer_profiles",
        "escalation_requests",
        "floors",
        "incident_notes",
        "incident_status_history",
        "incidents",
        "notifications",
        "refresh_tokens",
        "seats",
        "users",
    }
)

__all__ = [
    "AppSecret",
    "Base",
    "Building",
    "Category",
    "EXPECTED_TABLES",
    "EngineerProfile",
    "EscalationRequest",
    "EscalationStatus",
    "Floor",
    "Incident",
    "IncidentNote",
    "IncidentStatus",
    "IncidentStatusHistory",
    "NoteVisibility",
    "Notification",
    "NotificationKind",
    "Priority",
    "RefreshToken",
    "Role",
    "Seat",
    "User",
]
