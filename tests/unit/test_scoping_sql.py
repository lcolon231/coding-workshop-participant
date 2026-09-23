"""Scoping as generated SQL, with no database.

Kept deliberately cheap and secondary: it exercises SQLAlchemy's codegen as
much as our rule, and a compiled string can look right while the predicate is
semantically wrong. tests/integration/test_scoping_db.py is the real evidence.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.dialects import postgresql

from acme_core.exceptions import Forbidden
from acme_core.models.enums import NoteVisibility, Role
from acme_core.models.incident import Incident, IncidentNote
from acme_core.scoping import scope_incidents, scope_notes, visible_incident_ids
from acme_core.security.principal import Principal

pytestmark = pytest.mark.unit


def principal(role: Role) -> Principal:
    return Principal(user_id=uuid.uuid4(), email="a@acme.inc", role=role, is_active=True)


def sql(statement: object) -> str:
    return str(statement.compile(dialect=postgresql.dialect()))  # type: ignore[attr-defined]


class TestIncidentScoping:
    def test_admin_is_unfiltered(self) -> None:
        assert "WHERE" not in sql(
            scope_incidents(select(Incident.id), principal(Role.FACILITY_ADMIN))
        )

    def test_employee_filters_on_reporter_only(self) -> None:
        statement = sql(scope_incidents(select(Incident.id), principal(Role.EMPLOYEE)))
        assert "reporter_id" in statement
        assert "assignee_id" not in statement

    def test_engineer_filters_on_assignee_only(self) -> None:
        statement = sql(scope_incidents(select(Incident.id), principal(Role.ENGINEER)))
        assert "assignee_id" in statement
        assert "reporter_id" not in statement

    def test_returns_a_new_statement(self) -> None:
        """Generative, so a caller cannot mutate the original by accident."""
        original = select(Incident.id)
        assert scope_incidents(original, principal(Role.EMPLOYEE)) is not original
        assert "WHERE" not in sql(original)

    def test_composes_with_existing_filters(self) -> None:
        """Successive where() clauses AND together, so a filter cannot widen scope."""
        statement = sql(
            scope_incidents(
                select(Incident.id).where(Incident.title == "x"), principal(Role.EMPLOYEE)
            )
        )
        assert " AND " in statement

    def test_composes_after_ordering_and_limits(self) -> None:
        statement = scope_incidents(
            select(Incident).order_by(Incident.created_at.desc()).limit(10),
            principal(Role.EMPLOYEE),
        )
        assert "reporter_id" in sql(statement)

    def test_an_unknown_role_fails_closed(self) -> None:
        """A role added without deciding its visibility must not see everything."""
        rogue = Principal(
            user_id=uuid.uuid4(), email="a@acme.inc", role="Overlord", is_active=True
        )
        with pytest.raises(Forbidden):
            scope_incidents(select(Incident.id), rogue)


class TestNoteScoping:
    @pytest.mark.parametrize(
        "role", [Role.FACILITY_ADMIN, Role.ENGINEER], ids=lambda r: r.name
    )
    def test_staff_see_internal_notes(self, role: Role) -> None:
        assert "visibility" not in sql(
            scope_notes(select(IncidentNote.id), principal(role))
        )

    def test_employees_see_only_public_notes(self) -> None:
        statement = sql(scope_notes(select(IncidentNote.id), principal(Role.EMPLOYEE)))
        assert "visibility" in statement

    def test_the_filter_names_the_public_value(self) -> None:
        compiled = select(IncidentNote.id).where(
            IncidentNote.visibility == NoteVisibility.PUBLIC
        )
        assert "visibility" in sql(compiled)


class TestSubqueryHelper:
    def test_builds_a_scoped_id_select(self) -> None:
        """Used to scope children whose own table has no reporter column."""
        statement = sql(visible_incident_ids(principal(Role.EMPLOYEE)))
        assert "incidents.id" in statement
        assert "reporter_id" in statement

    def test_admin_subquery_is_unfiltered(self) -> None:
        assert "WHERE" not in sql(visible_incident_ids(principal(Role.FACILITY_ADMIN)))
