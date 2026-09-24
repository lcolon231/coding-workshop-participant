"""Grading one incident against its D8 target (`acme_core.reporting`)."""

from __future__ import annotations

import datetime as dt

import pytest

from acme_core.models.enums import Priority
from acme_core.reporting import AT_RISK_FRACTION, SLA_TARGETS, SlaState, due_at, sla_state

pytestmark = pytest.mark.unit

CREATED = dt.datetime(2026, 9, 23, 9, 0, tzinfo=dt.UTC)


@pytest.mark.parametrize("priority", list(Priority))
def test_due_at_is_creation_plus_the_priority_target(priority: Priority) -> None:
    assert due_at(priority, CREATED) == CREATED + SLA_TARGETS[priority]


@pytest.mark.parametrize(
    ("elapsed", "expected"),
    [
        (dt.timedelta(0), SlaState.ON_TRACK),
        (dt.timedelta(hours=2, minutes=59), SlaState.ON_TRACK),
        (dt.timedelta(hours=3), SlaState.AT_RISK),  # 1 h of 4 h left: the boundary is at risk
        (dt.timedelta(hours=3, minutes=59), SlaState.AT_RISK),
        (dt.timedelta(hours=4), SlaState.AT_RISK),  # due exactly now is not yet breached
        (dt.timedelta(hours=4, seconds=1), SlaState.BREACHED),
        (dt.timedelta(days=3), SlaState.BREACHED),
    ],
)
def test_open_work_is_graded_against_the_clock(elapsed: dt.timedelta, expected: SlaState) -> None:
    assert sla_state(Priority.CRITICAL, CREATED, None, CREATED + elapsed) is expected


@pytest.mark.parametrize("priority", list(Priority))
def test_at_risk_starts_at_the_same_share_of_every_target(priority: Priority) -> None:
    target = SLA_TARGETS[priority]
    just_before = CREATED + target * (1 - AT_RISK_FRACTION) - dt.timedelta(seconds=1)
    just_after = CREATED + target * (1 - AT_RISK_FRACTION) + dt.timedelta(seconds=1)
    assert sla_state(priority, CREATED, None, just_before) is SlaState.ON_TRACK
    assert sla_state(priority, CREATED, None, just_after) is SlaState.AT_RISK


def test_finished_work_is_graded_by_when_it_finished_not_by_now() -> None:
    """A resolved incident stays "met" however long ago that was."""
    much_later = CREATED + dt.timedelta(days=30)
    within = CREATED + dt.timedelta(hours=20)
    late = CREATED + dt.timedelta(hours=25)
    assert sla_state(Priority.HIGH, CREATED, within, much_later) is SlaState.MET
    assert sla_state(Priority.HIGH, CREATED, late, much_later) is SlaState.MISSED


def test_finishing_exactly_on_the_deadline_meets_it() -> None:
    deadline = due_at(Priority.LOW, CREATED)
    assert sla_state(Priority.LOW, CREATED, deadline, deadline) is SlaState.MET
