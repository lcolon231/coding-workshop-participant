"""Constraints enforced by PostgreSQL, not merely declared in the models.

Compiled DDL is checked in the unit tier. This tier proves the database
actually rejects the rows it should, which is the only evidence that matters.
"""

from __future__ import annotations

import datetime as dt
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, StatementError
from sqlalchemy.orm import Session

from acme_core.models import (
    AppSecret,
    Building,
    Category,
    EngineerProfile,
    Floor,
    Incident,
    IncidentNote,
    NoteVisibility,
    Priority,
    RefreshToken,
    Role,
    Seat,
    User,
)

pytestmark = pytest.mark.integration


def make_user(session: Session, email: str = "a@acme.inc", **kw: object) -> User:
    user = User(
        email=email,
        full_name="Test User",
        password_hash="$2b$12$placeholder",
        role=kw.pop("role", Role.EMPLOYEE),
        **kw,
    )
    session.add(user)
    session.flush()
    return user


def make_building(session: Session, code: str = "HQ") -> Building:
    building = Building(code=code, name=f"Building {code}")
    session.add(building)
    session.flush()
    return building


class TestUniqueness:
    def test_email_is_unique(self, db_session: Session) -> None:
        make_user(db_session, "dup@acme.inc")
        with pytest.raises(IntegrityError):
            make_user(db_session, "dup@acme.inc")

    def test_floor_level_unique_per_building(self, db_session: Session) -> None:
        building = make_building(db_session)
        db_session.add(Floor(building_id=building.id, level=3))
        db_session.flush()
        db_session.add(Floor(building_id=building.id, level=3))
        with pytest.raises(IntegrityError):
            db_session.flush()

    def test_same_level_allowed_in_another_building(self, db_session: Session) -> None:
        """Every building has a third floor; that must not collide."""
        a, b = make_building(db_session, "AAA"), make_building(db_session, "BBB")
        db_session.add_all([Floor(building_id=a.id, level=3), Floor(building_id=b.id, level=3)])
        db_session.flush()

    def test_seat_code_unique_per_floor(self, db_session: Session) -> None:
        building = make_building(db_session)
        floor = Floor(building_id=building.id, level=1)
        db_session.add(floor)
        db_session.flush()
        db_session.add(Seat(floor_id=floor.id, code="A-01"))
        db_session.flush()
        db_session.add(Seat(floor_id=floor.id, code="A-01"))
        with pytest.raises(IntegrityError):
            db_session.flush()

    def test_same_seat_code_allowed_on_another_floor(self, db_session: Session) -> None:
        building = make_building(db_session)
        one, two = Floor(building_id=building.id, level=1), Floor(building_id=building.id, level=2)
        db_session.add_all([one, two])
        db_session.flush()
        db_session.add_all([Seat(floor_id=one.id, code="A-01"), Seat(floor_id=two.id, code="A-01")])
        db_session.flush()

    def test_engineer_profile_is_one_to_one(self, db_session: Session) -> None:
        user = make_user(db_session, "eng@acme.inc", role=Role.ENGINEER)
        db_session.add(EngineerProfile(user_id=user.id, specialty="HVAC"))
        db_session.flush()
        db_session.add(EngineerProfile(user_id=user.id, specialty="Electrical"))
        with pytest.raises(IntegrityError):
            db_session.flush()

    def test_refresh_token_hash_is_unique(self, db_session: Session) -> None:
        user = make_user(db_session, "tok@acme.inc")
        expires = dt.datetime.now(dt.UTC) + dt.timedelta(days=7)
        for _ in range(2):
            db_session.add(
                RefreshToken(
                    user_id=user.id, token_hash="same", family_id=uuid.uuid4(), expires_at=expires
                )
            )
        with pytest.raises(IntegrityError):
            db_session.flush()

    def test_sibling_categories_cannot_share_a_name(self, db_session: Session) -> None:
        parent = Category(name="Facilities")
        db_session.add(parent)
        db_session.flush()
        db_session.add_all(
            [Category(name="HVAC", parent_id=parent.id), Category(name="HVAC", parent_id=parent.id)]
        )
        with pytest.raises(IntegrityError):
            db_session.flush()


class TestEnumChecks:
    def test_orm_rejects_an_invalid_role_before_the_database(self, db_session: Session) -> None:
        """validate_strings catches it client-side: the first of two defences."""
        with pytest.raises(StatementError, match="not among the defined enum values"):
            db_session.execute(
                User.__table__.insert().values(
                    id=uuid.uuid4(),
                    email="bad@acme.inc",
                    full_name="Bad",
                    password_hash="x",
                    role="Emperor",
                    is_active=True,
                    failed_login_count=0,
                )
            )

    def test_database_check_rejects_an_invalid_role(self, db_session: Session) -> None:
        """Raw SQL bypasses the ORM type, so this proves the CHECK really exists.

        Without it the previous test would still pass against an unconstrained
        VARCHAR -- which is exactly what SQLAlchemy emits by default, since
        Enum.create_constraint is False unless asked.
        """
        with pytest.raises(IntegrityError, match="ck_users_role"):
            db_session.execute(
                text(
                    "INSERT INTO users (id, email, full_name, password_hash, role, "
                    "is_active, sessions_valid_from, failed_login_count, "
                    "created_at, updated_at) VALUES "
                    "(gen_random_uuid(), 'raw@acme.inc', 'Raw', 'x', 'Emperor', "
                    "true, now(), 0, now(), now())"
                )
            )

    @pytest.mark.parametrize("role", list(Role))
    def test_every_declared_role_is_accepted(self, db_session: Session, role: Role) -> None:
        make_user(db_session, f"{role.name.lower()}@acme.inc", role=role)

    @pytest.mark.parametrize("priority", list(Priority))
    def test_every_priority_is_accepted(self, db_session: Session, priority: Priority) -> None:
        user = make_user(db_session, f"p{priority.name}@acme.inc")
        building = make_building(db_session, f"B{priority.name[:2]}")
        db_session.add(
            Incident(
                title="t",
                description="d",
                priority=priority,
                reporter_id=user.id,
                building_id=building.id,
            )
        )
        db_session.flush()


class TestIncidentLocation:
    def test_building_is_required(self, db_session: Session) -> None:
        user = make_user(db_session, "loc@acme.inc")
        db_session.add(Incident(title="t", description="d", reporter_id=user.id))
        with pytest.raises(IntegrityError):
            db_session.flush()

    def test_floor_and_seat_may_be_omitted(self, db_session: Session) -> None:
        """A lobby has no seat and a lift has no floor."""
        user = make_user(db_session, "lobby@acme.inc")
        building = make_building(db_session, "LOB")
        db_session.add(
            Incident(
                title="Lobby door", description="d", reporter_id=user.id, building_id=building.id
            )
        )
        db_session.flush()

    def test_dangling_building_is_rejected(self, db_session: Session) -> None:
        user = make_user(db_session, "dangle@acme.inc")
        db_session.add(
            Incident(title="t", description="d", reporter_id=user.id, building_id=uuid.uuid4())
        )
        with pytest.raises(IntegrityError):
            db_session.flush()


class TestStampDefaults:
    @pytest.mark.parametrize(
        "column", ["acknowledged_at", "assigned_at", "resolved_at", "closed_at"]
    )
    def test_stamps_start_null(self, db_session: Session, column: str) -> None:
        """A stamp must mean "this happened", never "this row was created"."""
        user = make_user(db_session, f"s{column}@acme.inc")
        building = make_building(db_session, f"S{column[:2]}")
        incident = Incident(
            title="t", description="d", reporter_id=user.id, building_id=building.id
        )
        db_session.add(incident)
        db_session.flush()
        assert getattr(incident, column) is None

    def test_created_at_is_populated_and_aware(self, db_session: Session) -> None:
        user = make_user(db_session, "tz@acme.inc")
        assert user.created_at.tzinfo is not None


class TestDeletePolicy:
    def test_reporter_cannot_be_deleted(self, db_session: Session) -> None:
        """RESTRICT: deleting a user must never erase incident history."""
        user = make_user(db_session, "reporter@acme.inc")
        building = make_building(db_session, "RES")
        db_session.add(
            Incident(title="t", description="d", reporter_id=user.id, building_id=building.id)
        )
        db_session.flush()
        # The violation surfaces on execute, not on the later flush. Match the
        # constraint name, not the wording: PostgreSQL 18 raises RestrictViolation
        # ("violates RESTRICT setting"), while 17 -- Aurora and the CI container --
        # raises the generic ForeignKeyViolation, which never says RESTRICT.
        with pytest.raises(IntegrityError, match="fk_incidents_reporter_id_users"):
            db_session.execute(User.__table__.delete().where(User.id == user.id))

    def test_notes_cascade_with_their_incident(self, db_session: Session) -> None:
        user = make_user(db_session, "notes@acme.inc")
        building = make_building(db_session, "NOT")
        incident = Incident(
            title="t", description="d", reporter_id=user.id, building_id=building.id
        )
        db_session.add(incident)
        db_session.flush()
        db_session.add(
            IncidentNote(
                incident_id=incident.id,
                author_id=user.id,
                body="b",
                visibility=NoteVisibility.INTERNAL,
            )
        )
        db_session.flush()
        db_session.execute(Incident.__table__.delete().where(Incident.id == incident.id))
        db_session.flush()
        remaining = db_session.query(IncidentNote).filter_by(incident_id=incident.id).count()
        assert remaining == 0


class TestPersistenceRoundTrip:
    def test_writes_are_visible_to_a_second_session(
        self, db_session: Session, verify_session: Session
    ) -> None:
        """Guards the identity-map trap: expire_on_commit=False can mask a
        write that never reached PostgreSQL."""
        make_user(db_session, "roundtrip@acme.inc")
        db_session.commit()
        found = verify_session.query(User).filter_by(email="roundtrip@acme.inc").one_or_none()
        assert found is not None

    def test_app_secret_upsert_is_race_safe(self, db_session: Session) -> None:
        """Two cold Lambdas can reach the secret bootstrap at the same time."""
        from sqlalchemy.dialects.postgresql import insert

        stmt = (
            insert(AppSecret)
            .values(name="jwt", value="first")
            .on_conflict_do_nothing(index_elements=["name"])
        )
        db_session.execute(stmt)
        db_session.execute(stmt.values(name="jwt", value="second"))
        db_session.flush()
        stored = db_session.get(AppSecret, "jwt")
        assert stored is not None and stored.value == "first"
