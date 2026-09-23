"""Domain enumerations.

Stored as VARCHAR with a CHECK constraint rather than as native PostgreSQL
ENUM types. Native enums require ALTER TYPE to change, which Alembic cannot
autogenerate and which cannot run inside a transaction on older servers; a
constrained string keeps migrations reversible and readable in `psql`.
"""

from enum import StrEnum


class Role(StrEnum):
    """What a user may do across the platform."""

    EMPLOYEE = "Employee"
    FACILITY_ADMIN = "Facility Admin"
    ENGINEER = "Engineer"


class IncidentStatus(StrEnum):
    """Lifecycle position of an incident.

    The legal moves between these live in `acme_core.workflow`, as data. The
    values are the display strings so a database row is readable without a
    lookup table.
    """

    OPEN = "Open"
    IN_PROGRESS = "In Progress"
    BLOCKED = "Blocked"
    RESOLVED = "Resolved"
    CLOSED = "Closed"


class Priority(StrEnum):
    """How urgently an incident needs attention."""

    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"
    CRITICAL = "Critical"


class NoteVisibility(StrEnum):
    """Who may read a note.

    `INTERNAL` notes are visible to Facility Admins and Engineers only; the
    filter lives in `acme_core.scoping`, not in the route handlers.
    """

    PUBLIC = "public"
    INTERNAL = "internal"


class EscalationStatus(StrEnum):
    """Outcome of a request to escalate an incident."""

    PENDING = "Pending"
    APPROVED = "Approved"
    REJECTED = "Rejected"


class NotificationKind(StrEnum):
    """Why a user is being told about an incident.

    `ASSIGNED` goes to the engineer an incident was just assigned to;
    `REPORTED` goes to every active Facility Admin when one is filed.
    """

    ASSIGNED = "Assigned"
    REPORTED = "Reported"
