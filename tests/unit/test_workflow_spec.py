"""The specification, written by hand and compared against the table.

Every other workflow test derives its expectations from `EXPECTED` below. That
is the point: a test that read `TRANSITIONS` to decide what `TRANSITIONS`
should contain would pass no matter what the table said. This one file is the
independent statement of intent, transcribed from the brief, and editing the
table without editing it here fails the suite.
"""

from __future__ import annotations

import pytest

from acme_core.models.enums import IncidentStatus as S
from acme_core.workflow import TRANSITIONS, Actor

pytestmark = pytest.mark.unit

# (source, target, allowed actors, fields the caller must supply or have set)
EXPECTED: frozenset[tuple[S, S, frozenset[Actor], frozenset[str]]] = frozenset(
    {
        (S.OPEN, S.IN_PROGRESS, frozenset({Actor.ADMIN, Actor.ANY_ENGINEER}),
         frozenset({"assignee_id"})),
        (S.OPEN, S.CLOSED, frozenset({Actor.ADMIN}),
         frozenset({"resolution_note"})),
        (S.IN_PROGRESS, S.BLOCKED, frozenset({Actor.ADMIN, Actor.ASSIGNED_ENGINEER}),
         frozenset({"blocked_reason"})),
        (S.BLOCKED, S.IN_PROGRESS, frozenset({Actor.ADMIN, Actor.ASSIGNED_ENGINEER}),
         frozenset()),
        (S.IN_PROGRESS, S.RESOLVED, frozenset({Actor.ADMIN, Actor.ASSIGNED_ENGINEER}),
         frozenset({"resolution_note"})),
        (S.RESOLVED, S.CLOSED, frozenset({Actor.ADMIN, Actor.REPORTER}),
         frozenset()),
        (S.RESOLVED, S.IN_PROGRESS, frozenset({Actor.ADMIN, Actor.REPORTER}),
         frozenset()),
    }
)

# Derived views, so no other test has to restate the specification.
LEGAL: dict[tuple[S, S], tuple[frozenset[Actor], frozenset[str]]] = {
    (source, target): (actors, requires) for source, target, actors, requires in EXPECTED
}


def test_the_table_matches_the_specification() -> None:
    """The single assertion the other ~400 workflow cases rest on."""
    actual = frozenset(
        (
            rule.source,
            rule.target,
            rule.allowed_actors,
            rule.required_payload | rule.required_state,
        )
        for rule in TRANSITIONS
    )
    assert actual == EXPECTED


def test_exactly_seven_edges() -> None:
    assert len(TRANSITIONS) == len(EXPECTED) == 7


def test_closed_is_terminal_by_omission() -> None:
    """Not by a special case. Nothing in the module names CLOSED as an exception."""
    assert [rule for rule in TRANSITIONS if rule.source is S.CLOSED] == []


def test_no_duplicate_edges() -> None:
    edges = [(rule.source, rule.target) for rule in TRANSITIONS]
    assert len(edges) == len(set(edges))


def test_no_self_loops() -> None:
    assert [rule for rule in TRANSITIONS if rule.source is rule.target] == []


def test_every_status_is_reachable_from_open() -> None:
    """A status nothing can reach is dead weight in the model."""
    reachable = {S.OPEN}
    changed = True
    while changed:
        changed = False
        for rule in TRANSITIONS:
            if rule.source in reachable and rule.target not in reachable:
                reachable.add(rule.target)
                changed = True
    assert reachable == set(S)


class TestDescribe:
    """The payload for GET /api/incidents/workflow.

    The client renders buttons from this, so its shape is a contract.
    """

    def test_lists_every_status(self) -> None:
        from acme_core.workflow import describe

        assert describe()["statuses"] == [status.value for status in S]

    def test_lists_every_edge(self) -> None:
        from acme_core.workflow import describe

        assert len(describe()["transitions"]) == len(EXPECTED)

    def test_each_edge_carries_what_a_client_needs(self) -> None:
        from acme_core.workflow import describe

        for edge in describe()["transitions"]:
            assert set(edge) == {"from", "to", "label", "allowed_actors", "requires"}

    def test_requirements_are_reported_so_the_ui_can_prompt(self) -> None:
        """Without this the client cannot know to ask for a resolution note."""
        from acme_core.workflow import describe

        by_edge = {(e["from"], e["to"]): e for e in describe()["transitions"]}
        assert by_edge[("Open", "Closed")]["requires"] == ["resolution_note"]
        assert by_edge[("Blocked", "In Progress")]["requires"] == []

    def test_is_json_serialisable(self) -> None:
        """It is returned straight from a route; enums would not survive."""
        import json

        from acme_core.workflow import describe

        assert json.loads(json.dumps(describe()))["statuses"][0] == "Open"
