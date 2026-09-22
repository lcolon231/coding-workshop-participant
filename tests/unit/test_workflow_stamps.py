"""Lifecycle timestamps, and the reopen case that makes the policy matter."""

from __future__ import annotations

import datetime as dt

import pytest

from acme_core.models.enums import IncidentStatus as S
from acme_core.workflow import STAMP_ON_ENTER, StampPolicy, stamps_for

pytestmark = pytest.mark.unit

STAMPS = ("acknowledged_at", "assigned_at", "resolved_at", "closed_at")
FIRST = dt.datetime(2026, 1, 1, 9, 0, tzinfo=dt.UTC)
LATER = dt.datetime(2026, 3, 1, 15, 30, tzinfo=dt.UTC)
EMPTY: dict[str, dt.datetime | None] = dict.fromkeys(STAMPS)


class TestUnstamped:
    @pytest.mark.parametrize(
        ("target", "expected"),
        [
            (S.IN_PROGRESS, {"acknowledged_at", "assigned_at"}),
            (S.RESOLVED, {"resolved_at"}),
            (S.CLOSED, {"closed_at"}),
            (S.OPEN, set()),
            (S.BLOCKED, set()),
        ],
        ids=lambda v: v.value if isinstance(v, S) else str(v),
    )
    def test_entering_a_status_writes_its_stamps(
        self, target: S, expected: set[str]
    ) -> None:
        assert set(stamps_for(target, EMPTY, FIRST)) == expected

    @pytest.mark.parametrize("target", list(S), ids=lambda s: s.value)
    def test_only_declared_columns_are_touched(self, target: S) -> None:
        """A bug that sets the right stamp while clobbering another must fail."""
        assert set(stamps_for(target, EMPTY, FIRST)) <= set(STAMPS)


class TestFirstOccurrence:
    """acknowledged_at and assigned_at answer "how fast did anyone pick this up"."""

    @pytest.mark.parametrize("field", ["acknowledged_at", "assigned_at"])
    def test_an_existing_value_is_preserved(self, field: str) -> None:
        current = {**EMPTY, field: FIRST}
        assert field not in stamps_for(S.IN_PROGRESS, current, LATER)

    def test_returning_from_blocked_does_not_reset_acknowledgement(self) -> None:
        """Blocked -> In Progress is a normal part of one piece of work."""
        current = {**EMPTY, "acknowledged_at": FIRST, "assigned_at": FIRST}
        assert stamps_for(S.IN_PROGRESS, current, LATER) == {}


class TestLatestOccurrence:
    """resolved_at and closed_at answer "when did this finish"."""

    def test_reopening_and_resolving_again_overwrites(self) -> None:
        """Keeping the first value would report a time-to-resolve that silently
        excludes every hour of the second round of work."""
        current = {**EMPTY, "resolved_at": FIRST}
        assert stamps_for(S.RESOLVED, current, LATER) == {"resolved_at": LATER}

    def test_closing_again_overwrites(self) -> None:
        current = {**EMPTY, "closed_at": FIRST}
        assert stamps_for(S.CLOSED, current, LATER) == {"closed_at": LATER}


class TestPolicyTable:
    def test_acknowledgement_is_first_and_resolution_is_latest(self) -> None:
        """The distinction the whole module exists for."""
        assert STAMP_ON_ENTER[S.IN_PROGRESS]["acknowledged_at"] is StampPolicy.FIRST
        assert STAMP_ON_ENTER[S.RESOLVED]["resolved_at"] is StampPolicy.LATEST

    def test_every_stamped_column_is_on_the_incident_model(self) -> None:
        from acme_core.models import Incident

        declared = {f for fields in STAMP_ON_ENTER.values() for f in fields}
        assert declared <= set(Incident.__table__.columns.keys())

    def test_defaults_to_now_when_no_instant_given(self) -> None:
        before = dt.datetime.now(dt.UTC)
        stamped = stamps_for(S.RESOLVED, EMPTY)["resolved_at"]
        assert before <= stamped <= dt.datetime.now(dt.UTC)


class TestFullLifecycle:
    def test_a_reopened_ticket_reports_honest_timings(self) -> None:
        """The end-to-end reason the per-field policy exists."""
        incident: dict[str, dt.datetime | None] = dict(EMPTY)
        incident.update(stamps_for(S.IN_PROGRESS, incident, FIRST))
        incident.update(stamps_for(S.RESOLVED, incident, FIRST + dt.timedelta(hours=2)))
        # Reporter reopens it, an engineer works it again, it resolves later.
        incident.update(stamps_for(S.IN_PROGRESS, incident, LATER))
        incident.update(stamps_for(S.RESOLVED, incident, LATER + dt.timedelta(hours=1)))

        assert incident["acknowledged_at"] == FIRST
        assert incident["resolved_at"] == LATER + dt.timedelta(hours=1)
