"""Demo data: the accounts, places and incidents needed to walk through every role.

Three properties, each load-bearing:

- **No credential in source (S2).** This module ships inside the Lambda. The
  password arrives in the invoke payload (cloud) or the environment (local) and
  the seed refuses to run without it.
- **Idempotent.** Ids are `uuid5` of a fixed namespace and a natural key (an
  email, a building code, an incident title), so a re-run finds the same rows
  and creates nothing.
- **Strictly additive.** An existing row is never modified -- not a role, not
  a password, not an incident's status -- so re-seeding cannot undo an admin's
  changes or reset a password someone has since chosen.

Incident histories are not inserted as rows: each is a script of transitions
replayed through `workflow.validate_transition` with the real actor, so the
seed cannot produce a history the API could not have. A script that breaks
a rule fails the seed loudly rather than seeding impossible data.

Run locally with `make seed` (reads ACME_SEED_PASSWORD), in the cloud with
`make seed-cloud ADMIN_PASSWORD=...`.
"""

from __future__ import annotations

import datetime as dt
import os
import sys
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Final

from sqlalchemy import select
from sqlalchemy.orm import Session

from acme_core.models.catalog import Category
from acme_core.models.enums import IncidentStatus, Priority, Role
from acme_core.models.facility import Building, Floor, Seat
from acme_core.models.incident import Incident, IncidentStatusHistory
from acme_core.models.user import EngineerProfile, User
from acme_core.security.passwords import hash_password
from acme_core.workflow import (
    STAMP_ON_ENTER,
    TransitionContext,
    stamps_for,
    validate_transition,
)

# Fixed forever: changing it would make every re-seed create duplicates.
SEED_NAMESPACE: Final[uuid.UUID] = uuid.UUID("5d3c6f0e-8a41-4c38-9d2b-3f0a7c1e9b64")

PASSWORD_ENV: Final[str] = "ACME_SEED_PASSWORD"


def seed_id(kind: str, *parts: str) -> uuid.UUID:
    """The deterministic id of one seeded row, from its kind and natural key."""
    return uuid.uuid5(SEED_NAMESPACE, ":".join((kind, *parts)))


# --------------------------------------------------------------------------- users


@dataclass(frozen=True, slots=True)
class SeedUser:
    """One demo account."""

    email: str
    full_name: str
    role: Role
    date_of_birth: dt.date
    specialty: str | None = None
    occupation: str | None = None

    @property
    def id(self) -> uuid.UUID:
        """The deterministic id that makes re-seeding a no-op."""
        return seed_id("user", self.email)


ADMIN = "admin@acme.inc"
HVAC_ENGINEER = "hvac.engineer@acme.inc"
IT_ENGINEER = "it.engineer@acme.inc"
EMPLOYEE = "employee@acme.inc"
SECOND_EMPLOYEE = "second.employee@acme.inc"

SEED_USERS: Final[tuple[SeedUser, ...]] = (
    SeedUser(ADMIN, "Ada Admin", Role.FACILITY_ADMIN, dt.date(1984, 3, 12)),
    SeedUser(HVAC_ENGINEER, "Hank Vance", Role.ENGINEER, dt.date(1979, 7, 4), specialty="HVAC"),
    SeedUser(
        IT_ENGINEER, "Ivy Tran", Role.ENGINEER, dt.date(1991, 11, 23),
        specialty="Workplace Technology",
    ),
    SeedUser(
        EMPLOYEE, "Eve Employee", Role.EMPLOYEE, dt.date(1995, 1, 30),
        occupation="Financial Analyst",
    ),
    SeedUser(
        SECOND_EMPLOYEE, "Sam Second", Role.EMPLOYEE, dt.date(1988, 9, 17),
        occupation="Software Engineer",
    ),
)


# --------------------------------------------------------------------------- facilities


@dataclass(frozen=True, slots=True)
class SeedFloor:
    """One level of a seeded building, with its seat codes."""

    level: int
    name: str | None
    seats: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SeedBuilding:
    """One seeded site."""

    code: str
    name: str
    address: str
    floors: tuple[SeedFloor, ...]

    @property
    def id(self) -> uuid.UUID:
        """The deterministic id, from the code."""
        return seed_id("building", self.code)


SEED_BUILDINGS: Final[tuple[SeedBuilding, ...]] = (
    SeedBuilding(
        "HQ", "Headquarters", "1 Acme Way",
        floors=(
            SeedFloor(1, "Lobby and Reception", ("1-01", "1-02")),
            SeedFloor(2, "Engineering", ("2-01", "2-02", "2-03", "2-04")),
            SeedFloor(3, "Finance", ("3-01", "3-02", "3-03", "3-04")),
        ),
    ),
    SeedBuilding(
        "RVA", "Riverside Annex", "40 Quay Street",
        floors=(
            SeedFloor(1, None, ("1-01", "1-02")),
            SeedFloor(2, "Support", ("2-01", "2-02")),
        ),
    ),
)

# Parent -> children. The tree is two levels deep, like the model expects.
SEED_CATEGORIES: Final[Mapping[str, tuple[str, ...]]] = {
    "Facilities": ("HVAC", "Electrical", "Plumbing", "Cleaning"),
    "Workplace Technology": ("Monitor", "Network", "Printer", "Docking Station"),
}


# --------------------------------------------------------------------------- incidents


@dataclass(frozen=True, slots=True)
class SeedStep:
    """One transition in an incident's scripted history."""

    actor: str
    target: IncidentStatus
    hours_later: float
    payload: Mapping[str, str] = field(default_factory=dict)
    # Resolved to the engineer's real id at seed time, since a user someone
    # registered first keeps the id they were given.
    assignee: str | None = None


@dataclass(frozen=True, slots=True)
class SeedIncident:
    """One demo incident and the path it has taken so far."""

    title: str
    description: str
    reporter: str
    priority: Priority
    building: str
    days_ago: float
    category: tuple[str, str] | None = None
    floor: int | None = None
    seat: str | None = None
    steps: tuple[SeedStep, ...] = ()

    @property
    def id(self) -> uuid.UUID:
        """The deterministic id, from the title."""
        return seed_id("incident", self.title)


_START = IncidentStatus.IN_PROGRESS
SEED_INCIDENTS: Final[tuple[SeedIncident, ...]] = (
    SeedIncident(
        "Aircon dripping onto desk 3-02", "Water on the desk since about 9am.",
        EMPLOYEE, Priority.MEDIUM, "HQ", days_ago=0.2,
        category=("Facilities", "HVAC"), floor=3, seat="3-02",
    ),
    SeedIncident(
        "Monitor flickering at 2-03", "Left screen flickers every few minutes.",
        SECOND_EMPLOYEE, Priority.LOW, "HQ", days_ago=2,
        category=("Workplace Technology", "Monitor"), floor=2, seat="2-03",
        steps=(SeedStep(ADMIN, _START, 3, assignee=IT_ENGINEER),),
    ),
    SeedIncident(
        "Leaking tap in the second-floor kitchen", "Drips constantly; floor is wet.",
        EMPLOYEE, Priority.HIGH, "HQ", days_ago=4,
        category=("Facilities", "Plumbing"), floor=2,
        steps=(
            SeedStep(ADMIN, _START, 1, assignee=HVAC_ENGINEER),
            SeedStep(HVAC_ENGINEER, IncidentStatus.BLOCKED, 6,
                     {"blocked_reason": "Replacement cartridge on order."}),
        ),
    ),
    SeedIncident(
        "Printer jam on the Support floor", "Paper jams on every second job.",
        SECOND_EMPLOYEE, Priority.MEDIUM, "RVA", days_ago=6,
        category=("Workplace Technology", "Printer"), floor=2,
        steps=(
            SeedStep(ADMIN, _START, 2, assignee=IT_ENGINEER),
            SeedStep(IT_ENGINEER, IncidentStatus.RESOLVED, 20,
                     {"resolution_note": "Cleared the feed rollers and replaced the tray."}),
        ),
    ),
    SeedIncident(
        "Network down on floor 2", "Nobody on the floor can reach the file server.",
        EMPLOYEE, Priority.CRITICAL, "HQ", days_ago=12,
        category=("Workplace Technology", "Network"), floor=2,
        steps=(
            SeedStep(ADMIN, _START, 0.25, assignee=IT_ENGINEER),
            SeedStep(IT_ENGINEER, IncidentStatus.RESOLVED, 2.5,
                     {"resolution_note": "Reseated the uplink; switch rebooted."}),
            SeedStep(EMPLOYEE, IncidentStatus.CLOSED, 30),
        ),
    ),
    SeedIncident(
        "Flickering light in the lobby", "One tube over reception flickers.",
        SECOND_EMPLOYEE, Priority.LOW, "HQ", days_ago=20,
        category=("Facilities", "Electrical"), floor=1,
        steps=(
            SeedStep(ADMIN, IncidentStatus.CLOSED, 4,
                     {"resolution_note": "Duplicate of the lobby relamping job."}),
        ),
    ),
)

_STAMP_FIELDS = frozenset(f for fields in STAMP_ON_ENTER.values() for f in fields)


# --------------------------------------------------------------------------- seeding


def _seed_users(session: Session, password_hash: str) -> tuple[int, int]:
    """Create any demo account that does not exist yet."""
    created = existing = 0
    for spec in SEED_USERS:
        found = session.execute(
            select(User).where((User.id == spec.id) | (User.email == spec.email))
        ).scalar_one_or_none()
        if found is not None:
            existing += 1
            continue
        user = User(
            id=spec.id,
            email=spec.email,
            full_name=spec.full_name,
            password_hash=password_hash,
            role=spec.role,
            occupation=spec.occupation,
            date_of_birth=spec.date_of_birth,
        )
        if spec.specialty is not None:
            user.engineer_profile = EngineerProfile(specialty=spec.specialty)
        session.add(user)
        created += 1
    session.flush()
    return created, existing


def _seed_facilities(session: Session) -> tuple[int, int]:
    """Create any building, floor or seat that does not exist yet."""
    created = existing = 0
    for spec in SEED_BUILDINGS:
        if session.get(Building, spec.id) is None:
            session.add(Building(id=spec.id, code=spec.code, name=spec.name, address=spec.address))
            created += 1
        else:
            existing += 1
        for floor in spec.floors:
            floor_id = seed_id("floor", spec.code, str(floor.level))
            if session.get(Floor, floor_id) is None:
                session.add(
                    Floor(id=floor_id, building_id=spec.id, level=floor.level, name=floor.name)
                )
                created += 1
            else:
                existing += 1
            for code in floor.seats:
                seat_id = seed_id("seat", spec.code, str(floor.level), code)
                if session.get(Seat, seat_id) is None:
                    session.add(Seat(id=seat_id, floor_id=floor_id, code=code))
                    created += 1
                else:
                    existing += 1
    session.flush()
    return created, existing


def _seed_categories(session: Session) -> tuple[int, int]:
    """Create any category that does not exist yet, parents before children."""
    created = existing = 0
    for parent, children in SEED_CATEGORIES.items():
        parent_id = seed_id("category", parent)
        if session.get(Category, parent_id) is None:
            session.add(Category(id=parent_id, name=parent))
            created += 1
        else:
            existing += 1
        for child in children:
            child_id = seed_id("category", parent, child)
            if session.get(Category, child_id) is None:
                session.add(Category(id=child_id, name=child, parent_id=parent_id))
                created += 1
            else:
                existing += 1
    session.flush()
    return created, existing


def _users_by_email(session: Session) -> dict[str, User]:
    """The demo accounts as they exist, whatever id they ended up with."""
    emails = [spec.email for spec in SEED_USERS]
    rows = session.execute(select(User).where(User.email.in_(emails))).scalars()
    return {user.email: user for user in rows}


def _replay(incident: Incident, step: SeedStep, users: Mapping[str, User], at: dt.datetime) -> None:
    """Apply one scripted transition exactly as the API would, or raise.

    Mirrors `incidents_service.service.transition`, which the seed cannot
    import: the legality check and the stamp policy are the shared parts,
    and they are what make an impossible history impossible here too.
    """
    actor = users[step.actor]
    payload: dict[str, Any] = dict(step.payload)
    if step.assignee is not None:
        payload["assignee_id"] = users[step.assignee].id
    context = TransitionContext(
        current=incident.status,
        actor_id=actor.id,
        actor_role=actor.role,
        reporter_id=incident.reporter_id,
        assignee_id=incident.assignee_id,
    )
    validate_transition(context, step.target, payload)

    if "assignee_id" in payload:
        incident.assignee_id = payload["assignee_id"]
    if step.target is IncidentStatus.BLOCKED:
        incident.blocked_reason = payload["blocked_reason"]
    elif incident.status is IncidentStatus.BLOCKED:
        incident.blocked_reason = None
    if payload.get("resolution_note"):
        incident.resolution_note = payload["resolution_note"]
    current = {name: getattr(incident, name) for name in _STAMP_FIELDS}
    for name, moment in stamps_for(step.target, current, at).items():
        setattr(incident, name, moment)
    incident.status_history.append(
        IncidentStatusHistory(
            from_status=incident.status,
            to_status=step.target,
            actor_id=actor.id,
            note=payload.get("resolution_note") or payload.get("blocked_reason"),
            created_at=at,
        )
    )
    incident.status = step.target
    incident.updated_at = at


def _seed_incidents(session: Session, now: dt.datetime) -> tuple[int, int]:
    """Create any demo incident that does not exist yet, history included."""
    users = _users_by_email(session)
    created = existing = 0
    for spec in SEED_INCIDENTS:
        if session.get(Incident, spec.id) is not None:
            existing += 1
            continue
        building = next(b for b in SEED_BUILDINGS if b.code == spec.building)
        opened_at = now - dt.timedelta(days=spec.days_ago)
        incident = Incident(
            id=spec.id,
            title=spec.title,
            description=spec.description,
            status=IncidentStatus.OPEN,
            priority=spec.priority,
            reporter_id=users[spec.reporter].id,
            category_id=seed_id("category", *spec.category) if spec.category else None,
            building_id=building.id,
            floor_id=seed_id("floor", spec.building, str(spec.floor)) if spec.floor else None,
            seat_id=(
                seed_id("seat", spec.building, str(spec.floor), spec.seat) if spec.seat else None
            ),
            created_at=opened_at,
            updated_at=opened_at,
        )
        incident.status_history.append(
            IncidentStatusHistory(
                from_status=None,
                to_status=IncidentStatus.OPEN,
                actor_id=incident.reporter_id,
                created_at=opened_at,
            )
        )
        at = opened_at
        for step in spec.steps:
            at += dt.timedelta(hours=step.hours_later)
            _replay(incident, step, users, at)
        session.add(incident)
        created += 1
    session.flush()
    return created, existing


def seed(session: Session, password: str, now: dt.datetime | None = None) -> dict[str, int]:
    """Create whatever demo data does not exist yet.

    Args:
        session: An open session. The caller commits.
        password: The password for newly created accounts. Checked against the
            normal strength rules, so a demo cannot run on `admin`.
        now: The instant incident ages are measured from; defaults to now.

    Returns:
        How many rows of each kind were created and how many already existed.
    """
    # Hashed once: bcrypt at cost 12 is ~0.3 s, and five accounts sharing one
    # demo password gain nothing from five different salts.
    password_hash = hash_password(password)
    users = _seed_users(session, password_hash)
    facilities = _seed_facilities(session)
    categories = _seed_categories(session)
    incidents = _seed_incidents(session, now or dt.datetime.now(dt.UTC))
    return {
        "users_created": users[0],
        "users_existing": users[1],
        "facilities_created": facilities[0],
        "facilities_existing": facilities[1],
        "categories_created": categories[0],
        "categories_existing": categories[1],
        "incidents_created": incidents[0],
        "incidents_existing": incidents[1],
    }


def main() -> int:
    """Seed the local database. Entry point for `python -m acme_core.seed`.

    Returns:
        A process exit code.
    """
    password = os.getenv(PASSWORD_ENV, "")
    if not password:
        print(  # noqa: T201
            f"set {PASSWORD_ENV} to the demo password (12+ characters); "
            "it is never stored in code",
            file=sys.stderr,
        )
        return 2

    from acme_core.db.engine import get_session_factory

    with get_session_factory()() as session:
        report = seed(session, password)
        session.commit()
    print(report)  # noqa: T201
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
