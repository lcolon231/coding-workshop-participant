"""The incident lifecycle, expressed as data rather than control flow.

Every rule about who may move a ticket where lives in `TRANSITIONS`. Nothing
else in the codebase branches on status: the routes call `validate_transition`,
the client renders `allowed_targets`, and the stamps come from `STAMP_ON_ENTER`.
Adding a status or an edge is a change to a table, not a hunt through handlers.

Imports no web framework, so the seed and the admin invocation path can use it
without dragging in FastAPI.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Final

from acme_core.exceptions import Forbidden, InvalidTransition, ValidationFailed
from acme_core.models.enums import IncidentStatus, Role


class Actor(StrEnum):
    """A *relationship* to one incident, not a role.

    Rules are written in these terms because "the assigned engineer may block
    it" is a statement about this incident, not about engineers generally.
    """

    ADMIN = "admin"
    ANY_ENGINEER = "any_engineer"
    ASSIGNED_ENGINEER = "assigned_engineer"
    REPORTER = "reporter"


class StampPolicy(StrEnum):
    """When a lifecycle timestamp should be written."""

    FIRST = "first"
    LATEST = "latest"


@dataclass(frozen=True, slots=True)
class TransitionRule:
    """One legal edge of the state machine."""

    source: IncidentStatus
    target: IncidentStatus
    allowed_actors: frozenset[Actor]
    # Keys the caller must supply, non-blank, in this request.
    required_payload: frozenset[str]
    # Attributes that must be set once the payload has been applied. Distinct
    # from required_payload so "needs an assignee" is satisfied either by an
    # already-assigned incident or by assigning one in the same request.
    required_state: frozenset[str]
    label: str


@dataclass(frozen=True, slots=True)
class TransitionContext:
    """Everything needed to judge one transition, independent of the ORM."""

    current: IncidentStatus
    actor_id: uuid.UUID
    actor_role: Role
    reporter_id: uuid.UUID
    assignee_id: uuid.UUID | None = None


TRANSITIONS: Final[tuple[TransitionRule, ...]] = (
    TransitionRule(
        IncidentStatus.OPEN,
        IncidentStatus.IN_PROGRESS,
        frozenset({Actor.ADMIN, Actor.ANY_ENGINEER}),
        frozenset(),
        frozenset({"assignee_id"}),
        "Acknowledge and start work",
    ),
    TransitionRule(
        IncidentStatus.OPEN,
        IncidentStatus.CLOSED,
        frozenset({Actor.ADMIN}),
        frozenset({"resolution_note"}),
        frozenset(),
        "Close without work",
    ),
    TransitionRule(
        IncidentStatus.IN_PROGRESS,
        IncidentStatus.BLOCKED,
        frozenset({Actor.ADMIN, Actor.ASSIGNED_ENGINEER}),
        frozenset({"blocked_reason"}),
        frozenset(),
        "Block on an external dependency",
    ),
    TransitionRule(
        IncidentStatus.BLOCKED,
        IncidentStatus.IN_PROGRESS,
        frozenset({Actor.ADMIN, Actor.ASSIGNED_ENGINEER}),
        frozenset(),
        frozenset(),
        "Unblock",
    ),
    TransitionRule(
        IncidentStatus.IN_PROGRESS,
        IncidentStatus.RESOLVED,
        frozenset({Actor.ADMIN, Actor.ASSIGNED_ENGINEER}),
        frozenset({"resolution_note"}),
        frozenset(),
        "Resolve",
    ),
    TransitionRule(
        IncidentStatus.RESOLVED,
        IncidentStatus.CLOSED,
        frozenset({Actor.ADMIN, Actor.REPORTER}),
        frozenset(),
        frozenset(),
        "Confirm and close",
    ),
    TransitionRule(
        IncidentStatus.RESOLVED,
        IncidentStatus.IN_PROGRESS,
        frozenset({Actor.ADMIN, Actor.REPORTER}),
        frozenset(),
        frozenset(),
        "Reopen - not actually fixed",
    ),
)

# Closed is terminal purely because no rule has source == CLOSED. There is no
# special case for it anywhere, and none should be added.
_BY_EDGE: Final[Mapping[tuple[IncidentStatus, IncidentStatus], TransitionRule]] = {
    (rule.source, rule.target): rule for rule in TRANSITIONS
}

# Which lifecycle timestamps to write on entering a status, and whether the
# first or the latest occurrence is the meaningful one.
#
# acknowledged_at and assigned_at answer "how quickly did anyone pick this up",
# so they keep their first value even when a ticket is reopened. resolved_at and
# closed_at answer "when did this finish", so a reopened ticket must overwrite
# them -- otherwise time-to-resolve silently excludes every hour of the second
# round of work.
STAMP_ON_ENTER: Final[Mapping[IncidentStatus, Mapping[str, StampPolicy]]] = {
    IncidentStatus.IN_PROGRESS: {
        "acknowledged_at": StampPolicy.FIRST,
        "assigned_at": StampPolicy.FIRST,
    },
    IncidentStatus.RESOLVED: {"resolved_at": StampPolicy.LATEST},
    IncidentStatus.CLOSED: {"closed_at": StampPolicy.LATEST},
}


def actors_for(context: TransitionContext) -> frozenset[Actor]:
    """Derive which relationships the acting user satisfies.

    Args:
        context: The actor and the incident they are acting on.

    Returns:
        Every `Actor` the caller qualifies as.
    """
    actors: set[Actor] = set()
    if context.actor_role is Role.FACILITY_ADMIN:
        # The entire admin bypass. Note what it is not: it does not add
        # ASSIGNED_ENGINEER or REPORTER, and it cannot create an edge.
        actors.add(Actor.ADMIN)
    if context.actor_role is Role.ENGINEER:
        actors.add(Actor.ANY_ENGINEER)
        if context.assignee_id is not None and context.assignee_id == context.actor_id:
            actors.add(Actor.ASSIGNED_ENGINEER)
    if context.reporter_id == context.actor_id:
        actors.add(Actor.REPORTER)
    return frozenset(actors)


def _blank(value: object) -> bool:
    """Return True when a value is absent or only whitespace."""
    return value is None or (isinstance(value, str) and not value.strip())


def validate_transition(
    context: TransitionContext,
    target: IncidentStatus,
    payload: Mapping[str, Any] | None = None,
) -> TransitionRule:
    """Authorise one transition, or raise explaining why not.

    Checks run in a fixed order -- edge, then actor, then fields -- and that
    order is what makes the admin rule fall out structurally: an admin passes
    the actor check by holding `Actor.ADMIN`, but reaches the field check
    exactly like anyone else, and cannot conjure an edge that does not exist.

    Args:
        context: Actor and current incident state.
        target: The status being requested.
        payload: Values supplied with the request.

    Returns:
        The rule that authorised the move.

    Raises:
        InvalidTransition: No such edge, including every edge out of Closed.
        Forbidden: The edge exists but this actor may not take it.
        ValidationFailed: A required value is missing or blank.
    """
    values = dict(payload or {})
    rule = _BY_EDGE.get((context.current, target))
    if rule is None:
        raise InvalidTransition(
            f"Cannot move an incident from {context.current.value} to {target.value}."
        )

    if not (actors_for(context) & rule.allowed_actors):
        raise Forbidden(f"You may not {rule.label.lower()} on this incident.")

    missing = sorted(field for field in rule.required_payload if _blank(values.get(field)))
    if missing:
        raise ValidationFailed(
            f"{rule.label} requires: {', '.join(missing)}.",
            details=[{"field": field, "message": "This value is required."} for field in missing],
        )

    effective: dict[str, Any] = {"assignee_id": context.assignee_id, **values}
    missing_state = sorted(
        field for field in rule.required_state if _blank(effective.get(field))
    )
    if missing_state:
        raise ValidationFailed(
            f"{rule.label} requires: {', '.join(missing_state)}.",
            details=[
                {"field": field, "message": "This value is required."}
                for field in missing_state
            ],
        )
    return rule


def can_transition(
    context: TransitionContext,
    target: IncidentStatus,
    payload: Mapping[str, Any] | None = None,
) -> bool:
    """Report whether a transition would be allowed. Never raises.

    Args:
        context: Actor and current incident state.
        target: The status being requested.
        payload: Values that would be supplied.

    Returns:
        True when `validate_transition` would succeed.
    """
    try:
        validate_transition(context, target, payload)
    except (InvalidTransition, Forbidden, ValidationFailed):
        return False
    return True


def allowed_targets(
    context: TransitionContext,
    payload: Mapping[str, Any] | None = None,
) -> frozenset[IncidentStatus]:
    """List the statuses this actor may move to right now.

    Drives the client's button state. A UI offering an action the API will
    reject is a user-visible defect, and this is the single source both use.

    Args:
        context: Actor and current incident state.
        payload: Values the client would send; affects edges with requirements.

    Returns:
        The permitted target statuses, possibly empty.
    """
    return frozenset(
        rule.target
        for rule in TRANSITIONS
        if rule.source is context.current and can_transition(context, rule.target, payload)
    )


def stamps_for(
    target: IncidentStatus,
    current_values: Mapping[str, dt.datetime | None],
    now: dt.datetime | None = None,
) -> dict[str, dt.datetime]:
    """Compute the lifecycle timestamps to write when entering a status.

    Args:
        target: The status being entered.
        current_values: The incident's existing stamps.
        now: The instant to record; defaults to the current UTC time.

    Returns:
        Only the columns that should change, so a caller can apply them
        directly without re-checking policy.
    """
    moment = now or dt.datetime.now(dt.UTC)
    updates: dict[str, dt.datetime] = {}
    for field, policy in STAMP_ON_ENTER.get(target, {}).items():
        if policy is StampPolicy.LATEST or current_values.get(field) is None:
            updates[field] = moment
    return updates


def describe() -> dict[str, Any]:
    """Serialise the state machine for the client.

    Served at `GET /api/incidents/workflow` so the UI renders only legal
    actions and prompts for exactly the fields an edge requires.

    Returns:
        The statuses and the transition table.
    """
    return {
        "statuses": [status.value for status in IncidentStatus],
        "transitions": [
            {
                "from": rule.source.value,
                "to": rule.target.value,
                "label": rule.label,
                "allowed_actors": sorted(actor.value for actor in rule.allowed_actors),
                "requires": sorted(rule.required_payload | rule.required_state),
            }
            for rule in TRANSITIONS
        ],
    }
