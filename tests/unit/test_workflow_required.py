"""Required values, including the blank forms that slip past a truthiness check."""

from __future__ import annotations

import uuid
from itertools import product

import pytest

from acme_core.exceptions import ValidationFailed
from acme_core.models.enums import IncidentStatus as S
from acme_core.models.enums import Role
from acme_core.workflow import TransitionContext, validate_transition

from .test_workflow_spec import EXPECTED

pytestmark = pytest.mark.unit

ACTOR = uuid.UUID("55555555-5555-5555-5555-555555555555")

# Only payload requirements; assignee_id is state, covered in test_workflow_admin.
PAYLOAD_EDGES = [
    (source, target, sorted(requires - {"assignee_id"}))
    for source, target, _actors, requires in EXPECTED
    if requires - {"assignee_id"}
]
BLANKS = ("", "   ", "\t\n", None)


def admin(source: S) -> TransitionContext:
    return TransitionContext(
        current=source, actor_id=ACTOR, actor_role=Role.FACILITY_ADMIN,
        reporter_id=ACTOR, assignee_id=ACTOR,
    )


@pytest.mark.parametrize(
    ("edge", "blank"),
    list(product(PAYLOAD_EDGES, BLANKS)),
    ids=lambda v: f"{v[0].value}->{v[1].value}" if isinstance(v, tuple) else repr(v),
)
def test_blank_values_are_rejected(edge: tuple, blank: object) -> None:
    """A whitespace-only blocked_reason is the one everybody's code accepts."""
    source, target, fields = edge
    with pytest.raises(ValidationFailed):
        validate_transition(admin(source), target, dict.fromkeys(fields, blank))


@pytest.mark.parametrize(
    "edge", PAYLOAD_EDGES, ids=lambda e: f"{e[0].value}->{e[1].value}"
)
def test_a_real_value_is_accepted(edge: tuple) -> None:
    source, target, fields = edge
    validate_transition(admin(source), target, dict.fromkeys(fields, "a real reason"))


@pytest.mark.parametrize(
    "edge", PAYLOAD_EDGES, ids=lambda e: f"{e[0].value}->{e[1].value}"
)
def test_the_missing_field_is_named(edge: tuple) -> None:
    """The client renders these against the right input box."""
    source, target, fields = edge
    with pytest.raises(ValidationFailed) as exc:
        validate_transition(admin(source), target, {})
    assert {d["field"] for d in exc.value.details} == set(fields)


def test_unknown_payload_keys_are_ignored() -> None:
    """The workflow judges the fields it declares; schemas reject the rest."""
    validate_transition(admin(S.OPEN), S.CLOSED, {"resolution_note": "done", "junk": "x"})
