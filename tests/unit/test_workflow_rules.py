"""Every (from, to, role, relationship) cell, generated from the oracle.

5 statuses x 5 targets x 3 roles x 4 relationships = 300 cells, none written by
hand. Expectations come from `test_workflow_spec.EXPECTED`, never from
`TRANSITIONS`, so the matrix genuinely tests the table rather than agreeing
with it.
"""

from __future__ import annotations

import uuid
from itertools import product

import pytest

from acme_core.exceptions import Forbidden, InvalidTransition, ValidationFailed
from acme_core.models.enums import IncidentStatus as S
from acme_core.models.enums import Role
from acme_core.workflow import Actor, TransitionContext, actors_for, validate_transition

from .test_workflow_spec import LEGAL

pytestmark = pytest.mark.unit

ACTOR = uuid.UUID("11111111-1111-1111-1111-111111111111")
OTHER = uuid.UUID("22222222-2222-2222-2222-222222222222")

RELATIONSHIPS = ("stranger", "reporter", "assignee", "reporter_and_assignee")


def context(status: S, role: Role, relationship: str) -> TransitionContext:
    """Build a context placing the actor in a given relationship to the incident."""
    return TransitionContext(
        current=status,
        actor_id=ACTOR,
        actor_role=role,
        reporter_id=ACTOR if "reporter" in relationship else OTHER,
        assignee_id=ACTOR if "assignee" in relationship else OTHER,
    )


CELLS = list(product(list(S), list(S), list(Role), RELATIONSHIPS))


def cell_id(cell: tuple[S, S, Role, str]) -> str:
    source, target, role, relationship = cell
    return f"{source.value}->{target.value}[{role.value}/{relationship}]"


@pytest.mark.parametrize("cell", CELLS, ids=cell_id)
def test_cell_is_accepted_exactly_when_the_spec_allows(
    cell: tuple[S, S, Role, str],
) -> None:
    """The whole state machine, decided by the hand-written specification."""
    source, target, role, relationship = cell
    ctx = context(source, role, relationship)
    edge = LEGAL.get((source, target))
    # Supply every required field so only the edge and actor rules decide.
    payload = {field: "provided" for field in (edge[1] if edge else ())}
    payload.pop("assignee_id", None)  # comes from state, not payload

    if edge is None:
        with pytest.raises(InvalidTransition):
            validate_transition(ctx, target, payload)
        return

    allowed_actors, _ = edge
    if actors_for(ctx) & allowed_actors:
        validate_transition(ctx, target, payload)
    else:
        with pytest.raises(Forbidden):
            validate_transition(ctx, target, payload)


class TestTerminalState:
    @pytest.mark.parametrize("target", list(S), ids=lambda s: s.value)
    @pytest.mark.parametrize("role", list(Role), ids=lambda r: r.name)
    def test_nothing_leaves_closed(self, target: S, role: Role) -> None:
        """Including an admin: the bypass is over actors, never over edges."""
        ctx = context(S.CLOSED, role, "reporter_and_assignee")
        with pytest.raises(InvalidTransition):
            validate_transition(ctx, target, {"resolution_note": "x", "blocked_reason": "x"})


class TestCheckOrdering:
    """The order edge -> actor -> fields is what the admin rule rests on."""

    def test_a_missing_edge_beats_a_wrong_actor(self) -> None:
        ctx = context(S.OPEN, Role.EMPLOYEE, "stranger")
        with pytest.raises(InvalidTransition):
            validate_transition(ctx, S.BLOCKED)

    def test_a_wrong_actor_beats_a_missing_field(self) -> None:
        """Reporting the missing field first would leak which edges exist."""
        ctx = context(S.IN_PROGRESS, Role.EMPLOYEE, "stranger")
        with pytest.raises(Forbidden):
            validate_transition(ctx, S.RESOLVED, {})


class TestActorDerivation:
    """`actors_for` underpins the matrix, so it gets its own hand-written table."""

    @pytest.mark.parametrize(
        ("role", "relationship", "expected"),
        [
            (Role.EMPLOYEE, "stranger", frozenset()),
            (Role.EMPLOYEE, "reporter", frozenset({Actor.REPORTER})),
            (Role.EMPLOYEE, "assignee", frozenset()),
            (Role.EMPLOYEE, "reporter_and_assignee", frozenset({Actor.REPORTER})),
            (Role.ENGINEER, "stranger", frozenset({Actor.ANY_ENGINEER})),
            (Role.ENGINEER, "reporter", frozenset({Actor.ANY_ENGINEER, Actor.REPORTER})),
            (Role.ENGINEER, "assignee",
             frozenset({Actor.ANY_ENGINEER, Actor.ASSIGNED_ENGINEER})),
            (Role.ENGINEER, "reporter_and_assignee",
             frozenset({Actor.ANY_ENGINEER, Actor.ASSIGNED_ENGINEER, Actor.REPORTER})),
            (Role.FACILITY_ADMIN, "stranger", frozenset({Actor.ADMIN})),
            (Role.FACILITY_ADMIN, "reporter", frozenset({Actor.ADMIN, Actor.REPORTER})),
            (Role.FACILITY_ADMIN, "assignee", frozenset({Actor.ADMIN})),
            (Role.FACILITY_ADMIN, "reporter_and_assignee",
             frozenset({Actor.ADMIN, Actor.REPORTER})),
        ],
        ids=lambda v: v if isinstance(v, str) else getattr(v, "name", str(v)),
    )
    def test_relationships_are_derived_correctly(
        self, role: Role, relationship: str, expected: frozenset[Actor]
    ) -> None:
        assert actors_for(context(S.OPEN, role, relationship)) == expected

    def test_an_employee_assignee_is_not_an_assigned_engineer(self) -> None:
        """Assignment does not confer engineer powers on an employee."""
        assert Actor.ASSIGNED_ENGINEER not in actors_for(
            context(S.IN_PROGRESS, Role.EMPLOYEE, "assignee")
        )

    def test_an_admin_is_not_implicitly_the_assignee(self) -> None:
        """The bypass adds ADMIN only; it never fakes another relationship."""
        assert actors_for(context(S.OPEN, Role.FACILITY_ADMIN, "stranger")) == frozenset(
            {Actor.ADMIN}
        )

    def test_unassigned_incident_grants_nobody_assigned_engineer(self) -> None:
        ctx = TransitionContext(
            current=S.IN_PROGRESS,
            actor_id=ACTOR,
            actor_role=Role.ENGINEER,
            reporter_id=OTHER,
            assignee_id=None,
        )
        assert Actor.ASSIGNED_ENGINEER not in actors_for(ctx)


class TestErrorTypes:
    """Each failure maps to a distinct status, so the client can react."""

    def test_unknown_edge_is_a_conflict(self) -> None:
        with pytest.raises(InvalidTransition) as exc:
            validate_transition(context(S.OPEN, Role.FACILITY_ADMIN, "stranger"), S.BLOCKED)
        assert exc.value.status == 409

    def test_wrong_actor_is_forbidden(self) -> None:
        with pytest.raises(Forbidden) as exc:
            validate_transition(context(S.OPEN, Role.EMPLOYEE, "reporter"), S.CLOSED,
                                {"resolution_note": "x"})
        assert exc.value.status == 403

    def test_missing_field_is_a_validation_error(self) -> None:
        with pytest.raises(ValidationFailed) as exc:
            validate_transition(context(S.OPEN, Role.FACILITY_ADMIN, "stranger"), S.CLOSED, {})
        assert exc.value.status == 400
        assert [d["field"] for d in exc.value.details] == ["resolution_note"]
