"""Reporting policy: SLA targets, how one incident is graded against them, and
the bounds on a report's date range.

Constants rather than a table (api.md D8). A per-category target would need a
schema change and an admin screen; four numbers in code are reviewable in one
diff and cannot drift between environments.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Mapping
from enum import StrEnum
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

# An open incident is "at risk" once this share of its target or less is
# left: one hour on a Critical, six on a High, eighteen on a Medium.
AT_RISK_FRACTION: Final[float] = 0.25


class SlaState(StrEnum):
    """Where an incident stands against its priority's target.

    The first three describe open work against the clock; the last two grade
    finished work by when it was resolved. A closed incident that was never
    resolved (an admin closing a duplicate, say) has no resolution time and is
    graded on its closing time instead, so nothing finished is left unstated.
    """

    ON_TRACK = "on_track"
    AT_RISK = "at_risk"
    BREACHED = "breached"
    MET = "met"
    MISSED = "missed"


def due_at(priority: Priority, created_at: dt.datetime) -> dt.datetime:
    """The instant an incident must be resolved by to meet its target."""
    return created_at + SLA_TARGETS[priority]


def sla_state(
    priority: Priority,
    created_at: dt.datetime,
    finished_at: dt.datetime | None,
    now: dt.datetime,
) -> SlaState:
    """Grade one incident against its target.

    Args:
        priority: Sets the target.
        created_at: When the clock started.
        finished_at: When it was resolved (or closed without resolution), or
            None while it is still open.
        now: The instant to judge open work at.

    Returns:
        The state; pure, so it can be tested without a clock.
    """
    deadline = due_at(priority, created_at)
    if finished_at is not None:
        return SlaState.MET if finished_at <= deadline else SlaState.MISSED
    if now > deadline:
        return SlaState.BREACHED
    if deadline - now <= SLA_TARGETS[priority] * AT_RISK_FRACTION:
        return SlaState.AT_RISK
    return SlaState.ON_TRACK
