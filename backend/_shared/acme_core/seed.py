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
# The six that walk through every status; the rest of the sixty follow.
_FIRST_INCIDENTS: Final[tuple[SeedIncident, ...]] = (
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

# The five moves an incident can make, as one-liners, so the sixty scripts
# below read as histories rather than as dataclass literals.


def _assign(engineer: str, hours_later: float = 2) -> SeedStep:
    """An admin acknowledges the report and hands it to an engineer."""
    return SeedStep(ADMIN, IncidentStatus.IN_PROGRESS, hours_later, assignee=engineer)


def _block(engineer: str, hours_later: float, reason: str) -> SeedStep:
    """The assigned engineer parks it on something outside their control."""
    return SeedStep(engineer, IncidentStatus.BLOCKED, hours_later, {"blocked_reason": reason})


def _unblock(engineer: str, hours_later: float) -> SeedStep:
    """The dependency cleared; work resumes."""
    return SeedStep(engineer, IncidentStatus.IN_PROGRESS, hours_later)


def _resolve(engineer: str, hours_later: float, note: str) -> SeedStep:
    """The assigned engineer says what was done."""
    return SeedStep(engineer, IncidentStatus.RESOLVED, hours_later, {"resolution_note": note})


def _reopen(reporter: str, hours_later: float) -> SeedStep:
    """The reporter disagrees that it is fixed."""
    return SeedStep(reporter, IncidentStatus.IN_PROGRESS, hours_later)


def _close(actor: str, hours_later: float, note: str | None = None) -> SeedStep:
    """The reporter confirms a resolution, or an admin closes an open report with a note."""
    payload = {"resolution_note": note} if note else {}
    return SeedStep(actor, IncidentStatus.CLOSED, hours_later, payload)


def _fixed(
    engineer: str,
    note: str,
    *,
    picked_up: float = 2,
    done: float = 20,
    confirmed_by: str | None = None,
    confirmed: float = 24,
) -> tuple[SeedStep, ...]:
    """The common path: assigned, resolved and, when `confirmed_by` is the reporter, closed."""
    steps = (_assign(engineer, picked_up), _resolve(engineer, done, note))
    if confirmed_by is not None:
        steps += (_close(confirmed_by, confirmed),)
    return steps


_HVAC: Final = ("Facilities", "HVAC")
_ELECTRICAL: Final = ("Facilities", "Electrical")
_PLUMBING: Final = ("Facilities", "Plumbing")
_CLEANING: Final = ("Facilities", "Cleaning")
_MONITOR: Final = ("Workplace Technology", "Monitor")
_NETWORK: Final = ("Workplace Technology", "Network")
_PRINTER: Final = ("Workplace Technology", "Printer")
_DOCK: Final = ("Workplace Technology", "Docking Station")

# Fifty-four more, so every list page, filter, report and SLA state has
# something in it. Ages run from an hour to twelve weeks; the newer an
# incident, the more likely it is still open.
_MORE_INCIDENTS: Final[tuple[SeedIncident, ...]] = (
    # ------------------------------------------------------------------ HVAC
    SeedIncident(
        "Cold draught at desk 2-01", "There is a constant cold draught from the vent overhead.",
        SECOND_EMPLOYEE, Priority.LOW, "HQ", days_ago=1, category=_HVAC, floor=2, seat="2-01",
    ),
    SeedIncident(
        "Meeting room 3B too warm all afternoon", "Reads 27 degrees by 2pm every day this week.",
        EMPLOYEE, Priority.MEDIUM, "HQ", days_ago=3, category=_HVAC, floor=3,
        steps=(_assign(HVAC_ENGINEER, 5),),
    ),
    SeedIncident(
        "Aircon rattling above the Finance desks", "A loud rattle whenever the fan speeds up.",
        EMPLOYEE, Priority.LOW, "HQ", days_ago=9, category=_HVAC, floor=3,
        steps=_fixed(HVAC_ENGINEER, "Tightened the loose grille and rebalanced the fan.", done=30),
    ),
    SeedIncident(
        "No heating in the Riverside support area", "Radiators cold since Monday; people in coats.",
        SECOND_EMPLOYEE, Priority.HIGH, "RVA", days_ago=15, category=_HVAC, floor=2,
        steps=(
            _assign(HVAC_ENGINEER, 1),
            _block(HVAC_ENGINEER, 4, "Boiler control board on back order from the supplier."),
            _unblock(HVAC_ENGINEER, 72),
            _resolve(HVAC_ENGINEER, 6, "Fitted the new control board and bled the radiators."),
            _close(SECOND_EMPLOYEE, 20),
        ),
    ),
    SeedIncident(
        "Thermostat on floor 2 stuck at 18 degrees",
        "The dial turns but the reading never changes.",
        EMPLOYEE, Priority.MEDIUM, "HQ", days_ago=33, category=_HVAC, floor=2,
        steps=_fixed(HVAC_ENGINEER, "Replaced the thermostat head.", confirmed_by=EMPLOYEE),
    ),
    SeedIncident(
        "Musty smell from the lobby vents", "Noticeable as soon as you walk in.",
        SECOND_EMPLOYEE, Priority.LOW, "HQ", days_ago=55, category=_HVAC, floor=1,
        steps=_fixed(
            HVAC_ENGINEER, "Cleaned the ducts and changed the filters.",
            picked_up=26, done=48, confirmed_by=SECOND_EMPLOYEE, confirmed=70,
        ),
    ),
    SeedIncident(
        "Server cupboard on floor 2 overheating", "Temperature alarm on the rack went off at 6am.",
        EMPLOYEE, Priority.CRITICAL, "HQ", days_ago=41, category=_HVAC, floor=2,
        steps=_fixed(
            HVAC_ENGINEER, "Cleared the blocked intake and reset the split unit.",
            picked_up=0.5, done=3, confirmed_by=EMPLOYEE, confirmed=4,
        ),
    ),
    # ------------------------------------------------------------ Electrical
    SeedIncident(
        "Power socket dead at 3-04", "Neither outlet under the desk works; tested with a lamp.",
        EMPLOYEE, Priority.MEDIUM, "HQ", days_ago=0.5, category=_ELECTRICAL, floor=3, seat="3-04",
    ),
    SeedIncident(
        "Lights out in the third-floor stairwell", "Pitch dark between floors 2 and 3.",
        SECOND_EMPLOYEE, Priority.HIGH, "HQ", days_ago=2.5, category=_ELECTRICAL, floor=3,
        steps=(_assign(HVAC_ENGINEER, 1),),
    ),
    SeedIncident(
        "Emergency exit sign flickering on floor 1",
        "The sign by the side door flickers constantly.",
        EMPLOYEE, Priority.HIGH, "HQ", days_ago=7, category=_ELECTRICAL, floor=1,
        steps=_fixed(HVAC_ENGINEER, "Replaced the sign's battery pack and LED board.", done=8),
    ),
    SeedIncident(
        "Tripping breaker in the Riverside kitchen",
        "Kettle and microwave together trip the circuit.",
        SECOND_EMPLOYEE, Priority.HIGH, "RVA", days_ago=19, category=_ELECTRICAL, floor=1,
        steps=_fixed(
            HVAC_ENGINEER, "Moved the microwave to its own circuit.",
            picked_up=3, done=26, confirmed_by=SECOND_EMPLOYEE,
        ),
    ),
    SeedIncident(
        "Buzzing from the ceiling light at 2-04", "A low buzz all day; worse when it is dimmed.",
        EMPLOYEE, Priority.LOW, "HQ", days_ago=27, category=_ELECTRICAL, floor=2, seat="2-04",
        steps=_fixed(
            HVAC_ENGINEER, "Swapped the failing driver.", picked_up=30, done=50,
                confirmed_by=EMPLOYEE,
        ),
    ),
    SeedIncident(
        "Extension leads daisy-chained under desk 1-02", "Three leads plugged into each other.",
        SECOND_EMPLOYEE, Priority.MEDIUM, "HQ", days_ago=48, category=_ELECTRICAL, floor=1,
        seat="1-02",
        steps=(_close(ADMIN, 5, "Sorted at the desk move; the leads have gone."),),
    ),
    SeedIncident(
        "Lift call button unlit on the ground floor",
        "The button still works but does not light up.",
        EMPLOYEE, Priority.MEDIUM, "HQ", days_ago=62, category=_ELECTRICAL, floor=1,
        steps=_fixed(
            HVAC_ENGINEER, "Lift contractor replaced the button assembly.",
            picked_up=4, done=120, confirmed_by=EMPLOYEE, confirmed=48,
        ),
    ),
    # -------------------------------------------------------------- Plumbing
    SeedIncident(
        "Toilet on floor 3 keeps running", "The cistern never stops refilling.",
        EMPLOYEE, Priority.MEDIUM, "HQ", days_ago=1.5, category=_PLUMBING, floor=3,
    ),
    SeedIncident(
        "No hot water in the Riverside washroom", "Only cold from every tap since Tuesday.",
        SECOND_EMPLOYEE, Priority.MEDIUM, "RVA", days_ago=5, category=_PLUMBING, floor=1,
        steps=(
            _assign(HVAC_ENGINEER, 2),
            _block(HVAC_ENGINEER, 5, "Waiting for the plumber's next site visit."),
        ),
    ),
    SeedIncident(
        "Blocked sink in the Engineering kitchenette", "Water sits in the sink for an hour.",
        EMPLOYEE, Priority.HIGH, "HQ", days_ago=11, category=_PLUMBING, floor=2,
        steps=_fixed(HVAC_ENGINEER, "Cleared the trap and flushed the line.", done=6),
    ),
    SeedIncident(
        "Water cooler on floor 1 not dispensing", "The light is on but nothing comes out.",
        SECOND_EMPLOYEE, Priority.LOW, "HQ", days_ago=24, category=_PLUMBING, floor=1,
        steps=_fixed(
            HVAC_ENGINEER, "Descaled the valve and replaced the filter.",
            picked_up=20, done=28, confirmed_by=SECOND_EMPLOYEE,
        ),
    ),
    SeedIncident(
        "Dripping ceiling in the Riverside stairwell", "Water coming through the ceiling tiles.",
        EMPLOYEE, Priority.CRITICAL, "RVA", days_ago=36, category=_PLUMBING, floor=2,
        steps=_fixed(
            HVAC_ENGINEER, "Repaired the split joint above and replaced two tiles.",
            picked_up=0.5, done=9, confirmed_by=EMPLOYEE, confirmed=12,
        ),
    ),
    SeedIncident(
        "Low water pressure on the second floor", "Taps barely trickle in the afternoon.",
        SECOND_EMPLOYEE, Priority.LOW, "HQ", days_ago=70, category=_PLUMBING, floor=2,
        steps=_fixed(
            HVAC_ENGINEER, "Cleaned the aerators; pressure is back to normal.",
            picked_up=48, done=30, confirmed_by=SECOND_EMPLOYEE, confirmed=96,
        ),
    ),
    # -------------------------------------------------------------- Cleaning
    SeedIncident(
        "Coffee spill on the carpet at 3-01", "A full mug; it will stain if left.",
        EMPLOYEE, Priority.LOW, "HQ", days_ago=0.3, category=_CLEANING, floor=3, seat="3-01",
    ),
    SeedIncident(
        "Bins overflowing in the Support area", "Not emptied since Friday.",
        SECOND_EMPLOYEE, Priority.MEDIUM, "RVA", days_ago=1, category=_CLEANING, floor=2,
        steps=(_assign(HVAC_ENGINEER, 3),),
    ),
    SeedIncident(
        "Sticky floor in the lobby", "Something spilled by the turnstiles overnight.",
        EMPLOYEE, Priority.LOW, "HQ", days_ago=6, category=_CLEANING, floor=1,
        steps=_fixed(HVAC_ENGINEER, "Mopped and degreased the area.", picked_up=1, done=2),
    ),
    SeedIncident(
        "Broken glass in the Riverside car park", "A smashed bottle by the bike racks.",
        SECOND_EMPLOYEE, Priority.HIGH, "RVA", days_ago=13, category=_CLEANING, floor=1,
        steps=_fixed(
            HVAC_ENGINEER, "Swept and disposed of the glass.",
            picked_up=0.5, done=1, confirmed_by=SECOND_EMPLOYEE, confirmed=3,
        ),
    ),
    SeedIncident(
        "Fridge on floor 2 needs clearing out", "Something in there has gone very bad.",
        EMPLOYEE, Priority.LOW, "HQ", days_ago=30, category=_CLEANING, floor=2,
        steps=_fixed(
            HVAC_ENGINEER, "Emptied, cleaned and put a clear-out notice on the door.",
            picked_up=6, done=18, confirmed_by=EMPLOYEE,
        ),
    ),
    SeedIncident(
        "Mould around the third-floor window", "Black mould spreading along the sill.",
        SECOND_EMPLOYEE, Priority.MEDIUM, "HQ", days_ago=44, category=_CLEANING, floor=3,
        steps=(
            _assign(HVAC_ENGINEER, 8),
            _block(HVAC_ENGINEER, 3, "Needs the window seal fixed first; contractor booked."),
            _unblock(HVAC_ENGINEER, 168),
            _resolve(HVAC_ENGINEER, 5, "Seal replaced and the sill treated and repainted."),
            _close(SECOND_EMPLOYEE, 40),
        ),
    ),
    SeedIncident(
        "Bird droppings on the entrance canopy",
        "The glass canopy is filthy and visible from inside.",
        EMPLOYEE, Priority.LOW, "HQ", days_ago=80, category=_CLEANING, floor=1,
        steps=_fixed(
            HVAC_ENGINEER, "Window cleaners did the canopy on their visit.",
            picked_up=50, done=140, confirmed_by=EMPLOYEE, confirmed=30,
        ),
    ),
    # --------------------------------------------------------------- Monitor
    SeedIncident(
        "Dead pixels on the monitor at 3-03", "A cluster of dead pixels in the top-left corner.",
        EMPLOYEE, Priority.LOW, "HQ", days_ago=0.8, category=_MONITOR, floor=3, seat="3-03",
    ),
    SeedIncident(
        "Second monitor missing at desk 2-02", "Only one screen on the desk since I moved here.",
        SECOND_EMPLOYEE, Priority.MEDIUM, "HQ", days_ago=2, category=_MONITOR, floor=2, seat="2-02",
        steps=(_assign(IT_ENGINEER, 4),),
    ),
    SeedIncident(
        "Monitor arm sagging at 1-01", "The arm drops slowly until the screen rests on the desk.",
        EMPLOYEE, Priority.LOW, "HQ", days_ago=8, category=_MONITOR, floor=1, seat="1-01",
        steps=_fixed(IT_ENGINEER, "Re-tensioned the gas spring.", done=26),
    ),
    SeedIncident(
        "Screen won't wake from sleep at RVA 2-01", "Has to be unplugged and plugged back in.",
        SECOND_EMPLOYEE, Priority.MEDIUM, "RVA", days_ago=17, category=_MONITOR, floor=2,
        seat="2-01",
        steps=_fixed(
            IT_ENGINEER, "Updated the monitor firmware.", picked_up=5, confirmed_by=SECOND_EMPLOYEE,
        ),
    ),
    SeedIncident(
        "Cracked monitor at 3-01 after the desk move", "A crack across the bottom of the panel.",
        EMPLOYEE, Priority.HIGH, "HQ", days_ago=29, category=_MONITOR, floor=3, seat="3-01",
        steps=_fixed(IT_ENGINEER, "Replaced the monitor from stock.", done=4,
            confirmed_by=EMPLOYEE),
    ),
    SeedIncident(
        "Wrong resolution on the boardroom display", "Everything is stretched on the big screen.",
        SECOND_EMPLOYEE, Priority.MEDIUM, "HQ", days_ago=52, category=_MONITOR, floor=3,
        steps=_fixed(
            IT_ENGINEER, "Set the display to native 4K and locked the scaling.",
            picked_up=3, done=2, confirmed_by=SECOND_EMPLOYEE, confirmed=6,
        ),
    ),
    SeedIncident(
        "Monitor at 2-01 shows a pink tint", "Whites look pink on the right-hand screen.",
        EMPLOYEE, Priority.LOW, "HQ", days_ago=66, category=_MONITOR, floor=2, seat="2-01",
        steps=(_close(ADMIN, 30, "Screen was replaced during the floor-wide monitor refresh."),),
    ),
    # --------------------------------------------------------------- Network
    SeedIncident(
        "Wi-Fi drops every few minutes on floor 3", "Calls keep freezing across the whole floor.",
        EMPLOYEE, Priority.HIGH, "HQ", days_ago=0.4, category=_NETWORK, floor=3,
    ),
    SeedIncident(
        "No network at the Riverside reception desk", "Visitor sign-in tablet cannot connect.",
        SECOND_EMPLOYEE, Priority.HIGH, "RVA", days_ago=1.2, category=_NETWORK, floor=1,
            seat="1-01",
        steps=(_assign(IT_ENGINEER, 1),),
    ),
    SeedIncident(
        "VPN keeps disconnecting from the Support floor",
        "Drops every 10 minutes since the weekend.",
        EMPLOYEE, Priority.MEDIUM, "RVA", days_ago=4.5, category=_NETWORK, floor=2,
        steps=(
            _assign(IT_ENGINEER, 2),
            _block(IT_ENGINEER, 6, "Waiting on the ISP to replace the faulty line card."),
        ),
    ),
    SeedIncident(
        "Slow file transfers in Engineering", "Copying to the share runs at a few MB/s.",
        SECOND_EMPLOYEE, Priority.MEDIUM, "HQ", days_ago=10, category=_NETWORK, floor=2,
        steps=_fixed(IT_ENGINEER, "Found a port negotiating at 100 Mb; replaced the patch lead."),
    ),
    SeedIncident(
        "Ethernet port dead at 2-04", "No link light with any cable.",
        EMPLOYEE, Priority.MEDIUM, "HQ", days_ago=21, category=_NETWORK, floor=2, seat="2-04",
        steps=_fixed(IT_ENGINEER, "Re-patched the port in the comms room.", confirmed_by=EMPLOYEE),
    ),
    SeedIncident(
        "Guest Wi-Fi password rejected in the lobby",
        "Visitors cannot get on with the printed code.",
        SECOND_EMPLOYEE, Priority.LOW, "HQ", days_ago=38, category=_NETWORK, floor=1,
        steps=_fixed(
            IT_ENGINEER, "Rotated the guest passphrase and reprinted the cards.",
            picked_up=6, done=3, confirmed_by=SECOND_EMPLOYEE,
        ),
    ),
    SeedIncident(
        "Whole of Riverside offline this morning", "Nothing works: no Wi-Fi, no wired, no phones.",
        EMPLOYEE, Priority.CRITICAL, "RVA", days_ago=58, category=_NETWORK, floor=1,
        steps=_fixed(
            IT_ENGINEER, "Core switch power supply failed; swapped in the spare.",
            picked_up=0.25, done=2, confirmed_by=EMPLOYEE, confirmed=3,
        ),
    ),
    SeedIncident(
        "Printer unreachable over the network on floor 3", "Print jobs sit in the queue forever.",
        SECOND_EMPLOYEE, Priority.MEDIUM, "HQ", days_ago=74, category=_NETWORK, floor=3,
        steps=_fixed(
            IT_ENGINEER, "The printer had picked up a new IP; pinned its DHCP reservation.",
            picked_up=4, done=5, confirmed_by=SECOND_EMPLOYEE,
        ),
    ),
    # --------------------------------------------------------------- Printer
    SeedIncident(
        "Printer on floor 3 out of toner", "Black toner empty; the light has been on for days.",
        EMPLOYEE, Priority.LOW, "HQ", days_ago=0.6, category=_PRINTER, floor=3,
    ),
    SeedIncident(
        "Riverside printer prints blank pages", "Every page comes out white.",
        SECOND_EMPLOYEE, Priority.MEDIUM, "RVA", days_ago=3.5, category=_PRINTER, floor=1,
        steps=(_assign(IT_ENGINEER, 3),),
    ),
    SeedIncident(
        "Duplex printing broken on the Finance printer", "Double-sided jobs come out single-sided.",
        EMPLOYEE, Priority.LOW, "HQ", days_ago=14, category=_PRINTER, floor=3,
        steps=_fixed(IT_ENGINEER, "Reinstalled the driver with the duplex unit enabled.", done=40),
    ),
    SeedIncident(
        "Printer on floor 2 streaking every page", "A grey band down the left of every page.",
        SECOND_EMPLOYEE, Priority.MEDIUM, "HQ", days_ago=23, category=_PRINTER, floor=2,
        steps=_fixed(IT_ENGINEER, "Replaced the drum unit.", confirmed_by=SECOND_EMPLOYEE),
    ),
    SeedIncident(
        "Scanner-to-email failing on the lobby printer", "Scans never arrive; the panel says sent.",
        EMPLOYEE, Priority.MEDIUM, "HQ", days_ago=46, category=_PRINTER, floor=1,
        steps=_fixed(
            IT_ENGINEER, "Updated the SMTP relay credentials on the device.",
            picked_up=8, done=6, confirmed_by=EMPLOYEE, confirmed=10,
        ),
    ),
    SeedIncident(
        "Paper tray 2 won't close on the Support printer", "The tray is jammed half open.",
        SECOND_EMPLOYEE, Priority.LOW, "RVA", days_ago=84, category=_PRINTER, floor=2,
        steps=_fixed(
            IT_ENGINEER, "Removed a bent sheet from the guide and reseated the tray.",
            picked_up=24, done=10, confirmed_by=SECOND_EMPLOYEE, confirmed=50,
        ),
    ),
    # ------------------------------------------------------- Docking Station
    SeedIncident(
        "Dock not charging the laptop at 2-03", "Screens work but the battery keeps draining.",
        SECOND_EMPLOYEE, Priority.MEDIUM, "HQ", days_ago=0.9, category=_DOCK, floor=2, seat="2-03",
    ),
    SeedIncident(
        "Docking station missing from hot desk 1-02 at Riverside",
        "Desk has a monitor but no dock.",
        EMPLOYEE, Priority.MEDIUM, "RVA", days_ago=2.2, category=_DOCK, floor=1, seat="1-02",
        steps=(_assign(IT_ENGINEER, 6),),
    ),
    SeedIncident(
        "Dock at 3-02 drops USB devices", "Keyboard and mouse disconnect a few times an hour.",
        SECOND_EMPLOYEE, Priority.LOW, "HQ", days_ago=12, category=_DOCK, floor=3, seat="3-02",
        steps=_fixed(IT_ENGINEER, "Updated the dock firmware and swapped the host cable."),
    ),
    SeedIncident(
        "Dock at RVA 2-02 only drives one screen", "The second monitor is never detected.",
        EMPLOYEE, Priority.MEDIUM, "RVA", days_ago=26, category=_DOCK, floor=2, seat="2-02",
        steps=_fixed(
            IT_ENGINEER, "Replaced the dock; the old one had a dead DisplayPort.",
            picked_up=5, done=22, confirmed_by=EMPLOYEE,
        ),
    ),
    SeedIncident(
        "Dock firmware prompt blocking sign-in at 2-02", "A firmware dialog appears on every boot.",
        SECOND_EMPLOYEE, Priority.HIGH, "HQ", days_ago=35, category=_DOCK, floor=2, seat="2-02",
        steps=_fixed(
            IT_ENGINEER, "Applied the firmware update and cleared the prompt.",
            picked_up=1, done=3, confirmed_by=SECOND_EMPLOYEE, confirmed=5,
        ),
    ),
    SeedIncident(
        "Loose power connector on the dock at 3-04", "Wiggling the cable makes the dock reboot.",
        EMPLOYEE, Priority.LOW, "HQ", days_ago=50, category=_DOCK, floor=3, seat="3-04",
        steps=(
            _assign(IT_ENGINEER, 10),
            _resolve(IT_ENGINEER, 20, "Replaced the power adapter."),
            _reopen(EMPLOYEE, 30),
            _resolve(IT_ENGINEER, 26,
                "The socket on the dock itself was loose; replaced the dock."),
            _close(EMPLOYEE, 18),
        ),
    ),
)

SEED_INCIDENTS: Final[tuple[SeedIncident, ...]] = _FIRST_INCIDENTS + _MORE_INCIDENTS

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

    handed_to = None
    if "assignee_id" in payload and payload["assignee_id"] != incident.assignee_id:
        handed_to = incident.assignee_id = payload["assignee_id"]
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
            assignee_id=handed_to,
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
