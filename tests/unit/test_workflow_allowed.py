"""`allowed_targets`, which the client uses to decide what to render.

A UI offering a button the API will reject is a user-visible defect, so this
must agree with `validate_transition` for every actor in every state.
"""

from __future__ import annotations

import uuid
from itertools import product

import pytest

from acme_core.models.enums import IncidentStatus as S
from acme_core.models.enums import Role
from acme_core.workflow import (
    TransitionContext,
    actors_for,
    allowed_targets,
    can_transition,
)

from .test_workflow_rules import RELATIONSHIPS, context

from .test_workflow_spec import LEGAL  # isort: skip

pytestmark = pytest.mark.unit

STATES = list(product(list(S), list(Role), RELATIONSHIPS))


def state_id(state: tuple[S, Role, str]) -> str:
    status, role, relationship = state
    return f"{status.value}[{role.value}/{relationship}]"


@pytest.mark.parametrize("state", STATES, ids=state_id)
def test_matches_the_specification(state: tuple[S, Role, str]) -> None:
    """Derived from the hand-written spec, not from the transition table."""
    status, role, relationship = state
    ctx = context(status, role, relationship)
    payload = {"resolution_note": "x", "blocked_reason": "x"}
    expected = {
        target
        for (source, target), (actors, _requires) in LEGAL.items()
        if source is status and actors_for(ctx) & actors
    }
    assert allowed_targets(ctx, payload) == expected


@pytest.mark.parametrize("state", STATES, ids=state_id)
def test_agrees_with_validate_transition(state: tuple[S, Role, str]) -> None:
    """The two must never disagree: one renders the button, the other honours it."""
    status, role, relationship = state
    ctx = context(status, role, relationship)
    payload = {"resolution_note": "x", "blocked_reason": "x"}
    for target in S:
        assert (target in allowed_targets(ctx, payload)) is can_transition(
            ctx, target, payload
        )


@pytest.mark.parametrize("role", list(Role), ids=lambda r: r.name)
def test_closed_offers_nothing_to_anyone(role: Role) -> None:
    ctx = context(S.CLOSED, role, "reporter_and_assignee")
    assert allowed_targets(ctx, {"resolution_note": "x"}) == frozenset()


def test_missing_required_fields_withdraw_the_option() -> None:
    """Without a note there is nothing to render for close-without-work."""
    ctx = context(S.OPEN, Role.FACILITY_ADMIN, "stranger")
    assert S.CLOSED not in allowed_targets(ctx, {})
    assert S.CLOSED in allowed_targets(ctx, {"resolution_note": "not reproducible"})


def test_an_unassigned_open_incident_cannot_be_started() -> None:
    ctx = TransitionContext(
        current=S.OPEN,
        actor_id=uuid.uuid4(),
        actor_role=Role.ENGINEER,
        reporter_id=uuid.uuid4(),
        assignee_id=None,
    )
    assert allowed_targets(ctx) == frozenset()


def test_can_transition_never_raises() -> None:
    """It is a predicate; raising would make call sites defensive."""
    ctx = context(S.CLOSED, Role.EMPLOYEE, "stranger")
    assert can_transition(ctx, S.OPEN) is False
