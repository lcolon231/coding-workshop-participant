"""notify the reporter

Revision ID: d7a1c3e5f209
Revises: 83edc3342052
Created: 2026-09-23 20:40:00.000000

Two more notification kinds, `Resolved` and `Closed`, for the reporter. The
column is a VARCHAR under a CHECK (see `acme_core.models.types.enum_type`),
so widening the enum means recreating the constraint; no data moves.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = 'd7a1c3e5f209'
down_revision: str | None = '83edc3342052'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# The bare name: the metadata's naming convention prefixes `ck_notifications_`.
CONSTRAINT = 'notificationkind'
BEFORE = "kind IN ('Assigned', 'Reported')"
AFTER = "kind IN ('Assigned', 'Reported', 'Resolved', 'Closed')"


def upgrade() -> None:
    """Apply the change."""
    op.drop_constraint(CONSTRAINT, 'notifications', type_='check')
    op.create_check_constraint(CONSTRAINT, 'notifications', AFTER)


def downgrade() -> None:
    """Revert the change. Rows of the newer kinds cannot survive the narrower check."""
    op.execute("DELETE FROM notifications WHERE kind IN ('Resolved', 'Closed')")
    op.drop_constraint(CONSTRAINT, 'notifications', type_='check')
    op.create_check_constraint(CONSTRAINT, 'notifications', BEFORE)
