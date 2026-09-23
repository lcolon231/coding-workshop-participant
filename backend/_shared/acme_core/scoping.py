"""Row-level visibility.

A role gate answers "may this caller use this endpoint". It does not answer
"may this caller see this row", and answering only the first is how one
employee reads another's incident by guessing an id. Every incident query goes
through here.

Out-of-scope rows are filtered out rather than rejected, so a single-item read
ends at `one_or_none()` returning None and the caller raises NotFound. There is
no code path that could emit 403 and thereby confirm the row exists -- the
property is structural rather than remembered.
"""

from __future__ import annotations

from typing import Any, TypeVar

from sqlalchemy import Select

from acme_core.exceptions import Forbidden
from acme_core.models.enums import NoteVisibility, Role
from acme_core.models.incident import Incident, IncidentNote
from acme_core.security.principal import Principal

_S = TypeVar("_S", bound=Select[Any])


def scope_incidents(
    statement: _S,
    principal: Principal,
    *,
    entity: type[Incident] = Incident,
) -> _S:
    """Narrow an incidents query to the rows this caller may see.

    Employees see what they reported. Engineers see only what is assigned to
    them, which includes nothing they reported themselves until an admin
    assigns it to them. Facility Admins see everything.

    Returns a new statement; SQLAlchemy 2.0 selects are generative, so this
    chains anywhere in construction -- before or after joins, filters and
    ordering -- and the caller cannot forget to reassign.

    Args:
        statement: Any select over incidents.
        principal: The authenticated caller.
        entity: The mapped class to filter on, for aliased joins.

    Returns:
        The narrowed statement.

    Raises:
        Forbidden: The caller's role is not one this function knows about,
            which means a role was added without deciding its visibility.
    """
    match principal.role:
        case Role.FACILITY_ADMIN:
            return statement
        case Role.ENGINEER:
            return statement.where(entity.assignee_id == principal.user_id)
        case Role.EMPLOYEE:
            return statement.where(entity.reporter_id == principal.user_id)
    # Fail closed. A new role defaulting to "sees everything" is the worst
    # possible outcome of forgetting to update this.
    raise Forbidden("Your role has no defined incident visibility.")


def scope_notes(
    statement: _S,
    principal: Principal,
    *,
    entity: type[IncidentNote] = IncidentNote,
) -> _S:
    """Hide internal notes from non-staff.

    Assumes the parent incident has already been scoped; this only removes
    notes the caller may not read on an incident they may.

    Args:
        statement: Any select over incident notes.
        principal: The authenticated caller.
        entity: The mapped class to filter on, for aliased joins.

    Returns:
        The narrowed statement.
    """
    if principal.is_staff:
        return statement
    return statement.where(entity.visibility == NoteVisibility.PUBLIC)


def visible_incident_ids(principal: Principal) -> Select[Any]:
    """Build a select of the incident ids this caller may see.

    For use as a subquery when scoping a child resource whose own table has no
    reporter or assignee column.

    Args:
        principal: The authenticated caller.

    Returns:
        A select of incident ids.
    """
    from sqlalchemy import select

    return scope_incidents(select(Incident.id), principal)
