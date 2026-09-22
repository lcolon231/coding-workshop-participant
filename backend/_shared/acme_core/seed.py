"""Demo data: the accounts needed to walk through every role.

Three properties, each load-bearing:

- **No credential in source (S2).** This module ships inside the Lambda. The
  password arrives in the invoke payload (cloud) or the environment (local) and
  the seed refuses to run without it.
- **Idempotent.** Ids are `uuid5` of a fixed namespace and the email, so a
  re-run finds the same rows and creates nothing.
- **Strictly additive.** An existing row is never modified -- not its role, not
  its password -- so re-seeding cannot undo an admin's changes or reset a
  password someone has since chosen.

Facilities, categories and incidents join this file when their services land.

Run locally with `make seed` (reads ACME_SEED_PASSWORD), in the cloud with
`make seed-cloud ADMIN_PASSWORD=...`.
"""

from __future__ import annotations

import datetime as dt
import os
import sys
import uuid
from dataclasses import dataclass
from typing import Final

from sqlalchemy import select
from sqlalchemy.orm import Session

from acme_core.models.enums import Role
from acme_core.models.user import EngineerProfile, User
from acme_core.security.passwords import hash_password

# Fixed forever: changing it would make every re-seed create duplicates.
SEED_NAMESPACE: Final[uuid.UUID] = uuid.UUID("5d3c6f0e-8a41-4c38-9d2b-3f0a7c1e9b64")

PASSWORD_ENV: Final[str] = "ACME_SEED_PASSWORD"


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
        return uuid.uuid5(SEED_NAMESPACE, self.email)


SEED_USERS: Final[tuple[SeedUser, ...]] = (
    SeedUser("admin@acme.inc", "Ada Admin", Role.FACILITY_ADMIN, dt.date(1984, 3, 12)),
    SeedUser(
        "hvac.engineer@acme.inc", "Hank Vance", Role.ENGINEER, dt.date(1979, 7, 4),
        specialty="HVAC",
    ),
    SeedUser(
        "it.engineer@acme.inc", "Ivy Tran", Role.ENGINEER, dt.date(1991, 11, 23),
        specialty="Workplace Technology",
    ),
    SeedUser(
        "employee@acme.inc", "Eve Employee", Role.EMPLOYEE, dt.date(1995, 1, 30),
        occupation="Financial Analyst",
    ),
    SeedUser(
        "second.employee@acme.inc", "Sam Second", Role.EMPLOYEE, dt.date(1988, 9, 17),
        occupation="Software Engineer",
    ),
)


def seed(session: Session, password: str) -> dict[str, int]:
    """Create any demo account that does not exist yet.

    Args:
        session: An open session. The caller commits.
        password: The password for newly created accounts. Checked against the
            normal strength rules, so a demo cannot run on `admin`.

    Returns:
        How many accounts were created and how many already existed.
    """
    # Hashed once: bcrypt at cost 12 is ~0.3 s, and five accounts sharing one
    # demo password gain nothing from five different salts.
    password_hash = hash_password(password)
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
    return {"users_created": created, "users_existing": existing}


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
