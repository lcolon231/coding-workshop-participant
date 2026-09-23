"""Row-level scoping against real rows.

The primary evidence for the visibility rules. A compiled-SQL assertion can
pass against a predicate that is semantically wrong; only executing it against
known data shows who actually sees what.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from acme_core.models import (
    Building,
    Incident,
    IncidentNote,
    NoteVisibility,
    Role,
    User,
)
from acme_core.scoping import scope_incidents, scope_notes
from acme_core.security.principal import Principal

pytestmark = pytest.mark.integration


@dataclass
class World:
    """Three incidents with different reporters and assignees."""

    alice: User
    bob: User
    engineer: User
    admin: User
    alices_incident: Incident
    bobs_incident: Incident
    assigned_to_engineer: Incident


def _user(session: Session, email: str, role: Role) -> User:
    user = User(
        email=email, full_name=email, password_hash="$2b$12$x", role=role
    )
    session.add(user)
    session.flush()
    return user


@pytest.fixture
def world(db_session: Session) -> World:
    alice = _user(db_session, "alice@acme.inc", Role.EMPLOYEE)
    bob = _user(db_session, "bob@acme.inc", Role.EMPLOYEE)
    engineer = _user(db_session, "eng@acme.inc", Role.ENGINEER)
    admin = _user(db_session, "admin@acme.inc", Role.FACILITY_ADMIN)
    building = Building(code="HQ", name="HQ")
    db_session.add(building)
    db_session.flush()

    def incident(title: str, reporter: User, assignee: User | None = None) -> Incident:
        row = Incident(
            title=title, description="d", reporter_id=reporter.id,
            assignee_id=assignee.id if assignee else None, building_id=building.id,
        )
        db_session.add(row)
        db_session.flush()
        return row

    return World(
        alice=alice, bob=bob, engineer=engineer, admin=admin,
        alices_incident=incident("alice's", alice),
        bobs_incident=incident("bob's", bob),
        assigned_to_engineer=incident("bob's, assigned", bob, engineer),
    )


def visible(session: Session, user: User) -> set[uuid.UUID]:
    """Return the incident ids this user can see."""
    principal = Principal.from_user(user)
    return set(session.scalars(scope_incidents(select(Incident.id), principal)).all())


class TestWhoSeesWhat:
    def test_an_employee_sees_only_their_own(self, db_session: Session, world: World) -> None:
        assert visible(db_session, world.alice) == {world.alices_incident.id}

    def test_an_employee_does_not_see_another_employees(
        self, db_session: Session, world: World
    ) -> None:
        assert world.bobs_incident.id not in visible(db_session, world.alice)

    def test_an_engineer_sees_assigned_work(
        self, db_session: Session, world: World
    ) -> None:
        assert world.assigned_to_engineer.id in visible(db_session, world.engineer)

    def test_an_engineer_does_not_see_unassigned_work(
        self, db_session: Session, world: World
    ) -> None:
        """Assignment, not the Engineer role, is what grants visibility."""
        assert world.alices_incident.id not in visible(db_session, world.engineer)

    def test_an_engineer_does_not_see_incidents_they_reported(
        self, db_session: Session, world: World
    ) -> None:
        """Reporting grants an engineer nothing; only an admin's assignment does."""
        own = Incident(
            title="engineer's own", description="d",
            reporter_id=world.engineer.id,
            building_id=world.alices_incident.building_id,
        )
        db_session.add(own)
        db_session.flush()
        assert own.id not in visible(db_session, world.engineer)

    def test_an_admin_sees_everything(self, db_session: Session, world: World) -> None:
        assert visible(db_session, world.admin) == {
            world.alices_incident.id,
            world.bobs_incident.id,
            world.assigned_to_engineer.id,
        }


class TestSingleItemReads:
    """404-not-403 is structural: the row is filtered out, so there is no
    branch that could return 403 and confirm it exists."""

    def test_an_out_of_scope_read_returns_nothing(
        self, db_session: Session, world: World
    ) -> None:
        statement = scope_incidents(
            select(Incident).where(Incident.id == world.bobs_incident.id),
            Principal.from_user(world.alice),
        )
        assert db_session.scalars(statement).one_or_none() is None

    def test_a_nonexistent_id_is_indistinguishable(
        self, db_session: Session, world: World
    ) -> None:
        """Both produce None, so the caller cannot tell them apart."""
        statement = scope_incidents(
            select(Incident).where(Incident.id == uuid.uuid4()),
            Principal.from_user(world.alice),
        )
        assert db_session.scalars(statement).one_or_none() is None

    def test_an_admin_reading_the_same_id_succeeds(
        self, db_session: Session, world: World
    ) -> None:
        """The pair that proves it: same id, one caller sees it, one does not."""
        statement = scope_incidents(
            select(Incident).where(Incident.id == world.bobs_incident.id),
            Principal.from_user(world.admin),
        )
        assert db_session.scalars(statement).one_or_none() is not None


class TestCountsAndFilters:
    def test_a_count_does_not_leak_out_of_scope_rows(
        self, db_session: Session, world: World
    ) -> None:
        """Pagination totals must go through the same helper, or the number
        itself discloses how many hidden incidents exist."""
        statement = scope_incidents(
            select(func.count()).select_from(Incident), Principal.from_user(world.alice)
        )
        assert db_session.scalar(statement) == 1

    def test_a_filter_cannot_widen_scope(
        self, db_session: Session, world: World
    ) -> None:
        """Successive where() clauses AND, so a user filter stays inside scope."""
        statement = scope_incidents(
            select(Incident.id).where(Incident.title.like("%bob%")),
            Principal.from_user(world.alice),
        )
        assert db_session.scalars(statement).all() == []


class TestInternalNotes:
    @pytest.fixture
    def noted(self, db_session: Session, world: World) -> World:
        for visibility in (NoteVisibility.PUBLIC, NoteVisibility.INTERNAL):
            db_session.add(
                IncidentNote(
                    incident_id=world.alices_incident.id,
                    author_id=world.engineer.id,
                    body=f"{visibility.value} note",
                    visibility=visibility,
                )
            )
        db_session.flush()
        return world

    def test_an_employee_sees_only_public_notes(
        self, db_session: Session, noted: World
    ) -> None:
        rows = db_session.scalars(
            scope_notes(select(IncidentNote), Principal.from_user(noted.alice))
        ).all()
        assert [n.visibility for n in rows] == [NoteVisibility.PUBLIC]

    @pytest.mark.parametrize("who", ["engineer", "admin"])
    def test_staff_see_both(self, db_session: Session, noted: World, who: str) -> None:
        rows = db_session.scalars(
            scope_notes(select(IncidentNote), Principal.from_user(getattr(noted, who)))
        ).all()
        assert len(rows) == 2

    def test_the_internal_body_never_reaches_an_employee(
        self, db_session: Session, noted: World
    ) -> None:
        rows = db_session.scalars(
            scope_notes(select(IncidentNote), Principal.from_user(noted.alice))
        ).all()
        assert all("internal" not in note.body for note in rows)
