"""Reporting policy: SLA targets and the bounds on a report's date range.

Constants rather than a table (api.md D8). A per-category target would need a
schema change and an admin screen; four numbers in code are reviewable in one
diff and cannot drift between environments.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Mapping
from typing import Final

from acme_core.models.enums import Priority

# Time from creation to resolution within which an incident meets its SLA.
SLA_TARGETS: Final[Mapping[Priority, dt.timedelta]] = {
    Priority.CRITICAL: dt.timedelta(hours=4),
    Priority.HIGH: dt.timedelta(hours=24),
    Priority.MEDIUM: dt.timedelta(days=3),
    Priority.LOW: dt.timedelta(days=7),
}

# A report covers the last 30 days unless asked otherwise.
DEFAULT_RANGE_DAYS: Final[int] = 30

# Bounded because every report is a scan of `incidents` over the range: an
# unbounded range is an unauthenticated-cost lever against a scale-to-zero
# database the moment any report is exposed more widely than to admins.
MAX_RANGE_DAYS: Final[int] = 366
