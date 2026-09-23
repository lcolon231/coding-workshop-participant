"""The admin rule: bypasses the actor check, never the required fields.

Written as a pair over the same seven edges so the two halves cannot drift
apart. A bypass that quietly grew to cover required fields would let an admin
resolve a ticket with no resolution note, which is the whole point of the rule.
"""

from __future__ import annotations

import uuid

import pytest

from acme_core.exceptions import InvalidTransition, ValidationFailed
from acme_core.models.enums import IncidentStatus as S
from acme_core.models.enums import Role
from acme_core.workflow import TransitionContext, validate_transition

from .test_workflow_spec import EXPECTED

pytestmark = pytest.mark.unit

ADMIN = uuid.UUID("33333333-3333-3333-3333-333333333333")
STRANGER = uuid.UUID("44444444-4444-4444-4444-444444444444")

EDGES = sorted(EXPECTED, key=lambda e: (e[0].value, e[1].value))
# Payload requirements only. assignee_id is *state*, satisfied by an already
# assigned incident, so omitting it from a request proves nothing here -- the
# unassigned case has its own test below.
WITH_REQUIREMENTS = [edge for edge in EDGES if edge[3] - {"assignee_id"}]


def edge_id(edge: tuple) -> str:
    return f"{edge[0].value}->{edge[1].value}"


def admin_context(source: S) -> TransitionContext:
    """An admin who is neither the reporter nor the assignee."""
    return TransitionContext(
        current=source,
        actor_id=ADMIN,
        actor_role=Role.FACILITY_ADMIN,
        reporter_id=STRANGER,
        assignee_id=STRANGER,
    )


@pytest.mark.parametrize("edge", EDGES, ids=edge_id)
def test_admin_bypasses_the_actor_constraint(edge: tuple) -> None:
    """An admin may take every edge without holding any relationship to it."""
    source, target, _actors, requires = edge
    payload = {field: "provided" for field in requires if field != "assignee_id"}
    ctx = admin_context(source)
    # "requires an assignee" is state, and this incident has one.
    validate_transition(ctx, target, payload)


@pytest.mark.parametrize("edge", WITH_REQUIREMENTS, ids=edge_id)
def test_admin_does_not_bypass_required_fields(edge: tuple) -> None:
    """The half that matters. Same edges, same admin, fields omitted."""
    source, target, _actors, requires = edge
    ctx = admin_context(source)
    with pytest.raises(ValidationFailed) as exc:
        validate_transition(ctx, target, {})
    assert exc.value.code == "validation_error"
    assert {d["field"] for d in exc.value.details} == set(requires) - {"assignee_id"}


@pytest.mark.parametrize("edge", EDGES, ids=edge_id)
def test_admin_cannot_invent_an_edge(edge: tuple) -> None:
    """The bypass is over actors only; the table still bounds what is possible."""
    source, target, _actors, _requires = edge
    illegal = next(
        candidate
        for candidate in S
        if (source, candidate) not in {(e[0], e[1]) for e in EXPECTED}
    )
    with pytest.raises(InvalidTransition):
        validate_transition(admin_context(source), illegal, {"resolution_note": "x"})


def test_admin_still_needs_an_assignee_to_start_work() -> None:
    """required_state is not bypassed either: unassigned means unassigned."""
    ctx = TransitionContext(
        current=S.OPEN,
        actor_id=ADMIN,
        actor_role=Role.FACILITY_ADMIN,
        reporter_id=STRANGER,
        assignee_id=None,
    )
    with pytest.raises(ValidationFailed) as exc:
        validate_transition(ctx, S.IN_PROGRESS, {})
    assert [d["field"] for d in exc.value.details] == ["assignee_id"]


def test_an_assignee_supplied_in_the_request_satisfies_it() -> None:
    """Which is what an admin assigning and starting in one step does."""
    ctx = TransitionContext(
        current=S.OPEN,
        actor_id=ADMIN,
        actor_role=Role.FACILITY_ADMIN,
        reporter_id=STRANGER,
        assignee_id=None,
    )
    validate_transition(ctx, S.IN_PROGRESS, {"assignee_id": STRANGER})
