"""The incidents service end to end: real routes, real rows, real tokens.

Sign-in goes through the auth service on the same test transaction, so every
request here carries a token the real login endpoint issued. Persistence is
asserted through `verify_session`, which has its own identity map, so a change
that never reached PostgreSQL cannot read as applied (hazard 3).

Coverage follows api.md §4 and the task list: every endpoint for every role
(T60), the 404/200 pair on the same id (T61), every legal edge with its
history rows and stamps plus the admin-triage journey (T62), and the filter,
sort and pagination rules (T63).
"""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass
from typing import Any

import pytest
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from acme_core.models import (
    Building,
    Category,
    EscalationRequest,
    Floor,
    Incident,
    IncidentNote,
    IncidentStatusHistory,
    Notification,
    Role,
    Seat,
    User,
)
from acme_core.reporting import SLA_TARGETS

pytestmark = pytest.mark.integration

P = "/api/incidents"
NIL = "00000000-0000-0000-0000-000000000000"


def bearer(tokens: dict[str, Any]) -> dict[str, str]:
    return {"Authorization": f"Bearer {tokens['access_token']}"}


# --------------------------------------------------------------------------- world


@dataclass
class World:
    """Enough facilities and people to exercise every rule."""

    building: Building
    inactive_building: Building
    floor: Floor
    seat: Seat
    other_floor: Floor
    category: Category
    inactive_category: Category
    employee: User
    other_employee: User
    engineer: User
    other_engineer: User
    inactive_engineer: User
    admin: User


@pytest.fixture
def world(db_session: Session, make_user: Any) -> World:
    building = Building(code="HQ", name="Headquarters")
    inactive_building = Building(code="OLD", name="Decommissioned", is_active=False)
    db_session.add_all([building, inactive_building])
    db_session.flush()
    floor = Floor(building_id=building.id, level=3, name="Third")
    other_floor = Floor(building_id=inactive_building.id, level=1)
    db_session.add_all([floor, other_floor])
    db_session.flush()
    seat = Seat(floor_id=floor.id, code="3-14")
    category = Category(name="HVAC")
    inactive_category = Category(name="Retired", is_active=False)
    db_session.add_all([seat, category, inactive_category])
    db_session.commit()
    return World(
        building=building,
        inactive_building=inactive_building,
        floor=floor,
        seat=seat,
        other_floor=other_floor,
        category=category,
        inactive_category=inactive_category,
        employee=make_user(email="emp@acme.inc"),
        other_employee=make_user(email="other.emp@acme.inc"),
        engineer=make_user(Role.ENGINEER, email="eng@acme.inc", specialty="HVAC"),
        other_engineer=make_user(Role.ENGINEER, email="other.eng@acme.inc"),
        inactive_engineer=make_user(Role.ENGINEER, email="gone.eng@acme.inc", is_active=False),
        admin=make_user(Role.FACILITY_ADMIN, email="admin@acme.inc"),
    )


class Actors:
    """Bearer headers per person, signed in lazily through the real login."""

    def __init__(self, world: World, sign_in: Any) -> None:
        self._world = world
        self._sign_in = sign_in
        self._cache: dict[str, dict[str, str]] = {}

    def __getattr__(self, name: str) -> dict[str, str]:
        if name not in self._cache:
            self._cache[name] = bearer(self._sign_in(getattr(self._world, name).email))
        return self._cache[name]


@pytest.fixture
def actors(world: World, sign_in: Any) -> Actors:
    return Actors(world, sign_in)


class Api:
    """Thin helpers over the incidents client that assert the happy path."""

    def __init__(self, client: TestClient, world: World) -> None:
        self.client = client
        self.world = world

    def report(self, headers: dict[str, str], **overrides: Any) -> dict[str, Any]:
        body = {
            "title": "Aircon dripping",
            "description": "Water on desk 3-14 since 9am",
            "building_id": str(self.world.building.id),
            **overrides,
        }
        resp = self.client.post(P, json=body, headers=headers)
        assert resp.status_code == 201, resp.text
        return resp.json()

    def move(
        self, headers: dict[str, str], incident_id: str, target: str, **fields: Any
    ) -> Response:
        return self.client.post(
            f"{P}/{incident_id}/transition",
            json={"target_status": target, **fields},
            headers=headers,
        )

    def moved(
        self, headers: dict[str, str], incident_id: str, target: str, **fields: Any
    ) -> dict[str, Any]:
        resp = self.move(headers, incident_id, target, **fields)
        assert resp.status_code == 200, resp.text
        return resp.json()

    def in_progress(self, actors: Actors, engineer: User | None = None) -> dict[str, Any]:
        """An incident reported by the employee, assigned and started by the engineer."""
        engineer = engineer or self.world.engineer
        incident = self.report(actors.employee)
        return self.moved(
            actors.admin, incident["id"], "In Progress", assignee_id=str(engineer.id)
        )

    def resolved(self, actors: Actors) -> dict[str, Any]:
        incident = self.in_progress(actors)
        return self.moved(actors.engineer, incident["id"], "Resolved", resolution_note="Fixed.")


@pytest.fixture
def api(incidents_client: TestClient, world: World) -> Api:
    return Api(incidents_client, world)


def history_of(session: Session, incident_id: str) -> list[IncidentStatusHistory]:
    return list(
        session.scalars(
            select(IncidentStatusHistory)
            .where(IncidentStatusHistory.incident_id == uuid.UUID(incident_id))
            .order_by(IncidentStatusHistory.created_at, IncidentStatusHistory.id)
        )
    )


def stored(session: Session, incident_id: str) -> Incident:
    row = session.get(Incident, uuid.UUID(incident_id), populate_existing=True)
    assert row is not None
    return row


# --------------------------------------------------------------------------- contract


class TestRouteContract:
    PUBLIC = {("GET", f"{P}/healthz"), ("GET", f"{P}/readyz")}

    def test_every_other_route_rejects_an_anonymous_caller(
        self, incidents_client: TestClient
    ) -> None:
        schema = incidents_client.get(f"{P}/openapi.json").json()
        checked = 0
        for path, operations in schema["paths"].items():
            for method in operations:
                if (method.upper(), path) in self.PUBLIC:
                    continue
                url = path.replace("{incident_id}", NIL).replace("{escalation_id}", NIL)
                resp = incidents_client.request(method.upper(), url, json={})
                assert resp.status_code == 401, f"{method.upper()} {path} -> {resp.status_code}"
                checked += 1
        assert checked == 22, "the protected-route count changed; update this test deliberately"

    def test_static_paths_are_not_swallowed_by_the_id_route(
        self, incidents_client: TestClient, actors: Actors
    ) -> None:
        """`/workflow` must match its own route, not `/{incident_id}` as a bad UUID."""
        assert incidents_client.get(f"{P}/workflow", headers=actors.employee).status_code == 200
        assert incidents_client.get(f"{P}/escalations", headers=actors.admin).status_code == 200
        assert (
            incidents_client.get(f"{P}/reports/summary", headers=actors.admin).status_code == 200
        )
        assert (
            incidents_client.get(f"{P}/notifications", headers=actors.employee).status_code == 200
        )


# --------------------------------------------------------------------------- create


class TestCreate:
    def test_opens_an_incident_with_its_first_history_row(
        self, api: Api, actors: Actors, world: World, verify_session: Session
    ) -> None:
        body = api.report(
            actors.employee,
            priority="High",
            category_id=str(world.category.id),
            floor_id=str(world.floor.id),
            seat_id=str(world.seat.id),
        )
        assert body["status"] == "Open"
        assert body["priority"] == "High"
        assert body["reporter_id"] == str(world.employee.id)
        assert body["reporter"] == {
            "id": str(world.employee.id), "full_name": world.employee.full_name, "role": "Employee"
        }
        assert body["assignee"] is None
        assert body["seat_id"] == str(world.seat.id)
        rows = history_of(verify_session, body["id"])
        assert [(r.from_status, r.to_status.value, r.actor_id) for r in rows] == [
            (None, "Open", world.employee.id)
        ]

    def test_sets_the_location_header(
        self, incidents_client: TestClient, actors: Actors, world: World
    ) -> None:
        resp = incidents_client.post(
            P,
            json={"title": "t", "description": "d", "building_id": str(world.building.id)},
            headers=actors.employee,
        )
        assert resp.headers["Location"] == f"{P}/{resp.json()['id']}"

    @pytest.mark.parametrize("who", ["engineer", "admin"])
    def test_every_role_may_report(self, api: Api, actors: Actors, who: str) -> None:
        api.report(getattr(actors, who))

    @pytest.mark.parametrize("field", ["reporter_id", "status", "id"])
    def test_a_server_controlled_field_is_refused(
        self, incidents_client: TestClient, actors: Actors, world: World, field: str
    ) -> None:
        resp = incidents_client.post(
            P,
            json={
                "title": "t", "description": "d", "building_id": str(world.building.id),
                field: str(world.admin.id),
            },
            headers=actors.employee,
        )
        assert resp.status_code == 400
        assert resp.json()["error"] == "validation_error"

    def test_an_unknown_building_is_a_field_error(
        self, incidents_client: TestClient, actors: Actors
    ) -> None:
        resp = incidents_client.post(
            P, json={"title": "t", "description": "d", "building_id": str(uuid.uuid4())},
            headers=actors.employee,
        )
        assert resp.status_code == 400
        assert resp.json()["details"] == [
            {"field": "building_id", "message": "Building does not exist or is not active."}
        ]

    def test_an_inactive_building_is_refused(
        self, incidents_client: TestClient, actors: Actors, world: World
    ) -> None:
        resp = incidents_client.post(
            P, json={"title": "t", "description": "d",
                     "building_id": str(world.inactive_building.id)},
            headers=actors.employee,
        )
        assert resp.status_code == 400
        assert resp.json()["details"][0]["field"] == "building_id"

    def test_a_floor_of_another_building_is_refused(
        self, incidents_client: TestClient, actors: Actors, world: World
    ) -> None:
        resp = incidents_client.post(
            P, json={"title": "t", "description": "d", "building_id": str(world.building.id),
                     "floor_id": str(world.other_floor.id)},
            headers=actors.employee,
        )
        assert resp.status_code == 400
        assert [d["field"] for d in resp.json()["details"]] == ["floor_id"]

    def test_a_seat_off_the_floor_is_refused(
        self, incidents_client: TestClient, actors: Actors, world: World, db_session: Session
    ) -> None:
        elsewhere = Seat(floor_id=world.other_floor.id, code="X")
        db_session.add(elsewhere)
        db_session.commit()
        resp = incidents_client.post(
            P, json={"title": "t", "description": "d", "building_id": str(world.building.id),
                     "floor_id": str(world.floor.id), "seat_id": str(elsewhere.id)},
            headers=actors.employee,
        )
        assert resp.status_code == 400
        assert [d["field"] for d in resp.json()["details"]] == ["seat_id"]

    def test_a_seat_without_a_floor_is_refused(
        self, incidents_client: TestClient, actors: Actors, world: World
    ) -> None:
        resp = incidents_client.post(
            P, json={"title": "t", "description": "d", "building_id": str(world.building.id),
                     "seat_id": str(world.seat.id)},
            headers=actors.employee,
        )
        assert resp.status_code == 400

    def test_every_bad_reference_is_reported_at_once(
        self, incidents_client: TestClient, actors: Actors, world: World
    ) -> None:
        resp = incidents_client.post(
            P, json={"title": "t", "description": "d", "building_id": str(uuid.uuid4()),
                     "floor_id": str(uuid.uuid4()), "category_id": str(uuid.uuid4())},
            headers=actors.employee,
        )
        assert [d["field"] for d in resp.json()["details"]] == [
            "building_id", "floor_id", "category_id"
        ]

    @pytest.mark.parametrize("which", ["missing", "inactive"])
    def test_a_bad_category_is_refused(
        self, incidents_client: TestClient, actors: Actors, world: World, which: str
    ) -> None:
        category = uuid.uuid4() if which == "missing" else world.inactive_category.id
        resp = incidents_client.post(
            P, json={"title": "t", "description": "d", "building_id": str(world.building.id),
                     "category_id": str(category)},
            headers=actors.employee,
        )
        assert resp.status_code == 400
        assert resp.json()["details"][0]["field"] == "category_id"


# --------------------------------------------------------------------------- list


class TestList:
    @pytest.fixture
    def seeded(self, api: Api, actors: Actors, world: World) -> dict[str, dict[str, Any]]:
        return {
            "mine": api.report(actors.employee, title="Mine", priority="Low"),
            "theirs": api.report(actors.other_employee, title="Theirs", priority="Critical"),
            "assigned": api.moved(
                actors.admin,
                api.report(actors.other_employee, title="Theirs, assigned", priority="High")["id"],
                "In Progress",
                assignee_id=str(world.engineer.id),
            ),
        }

    def test_an_employee_sees_only_their_own(
        self, incidents_client: TestClient, actors: Actors, seeded: dict[str, Any]
    ) -> None:
        body = incidents_client.get(P, headers=actors.employee).json()
        assert [i["title"] for i in body["items"]] == ["Mine"]
        assert body["total"] == 1

    def test_an_engineer_sees_only_what_is_assigned_to_them(
        self, incidents_client: TestClient, api: Api, actors: Actors, seeded: dict[str, Any]
    ) -> None:
        """Not even their own report, until an admin assigns it to them."""
        api.report(actors.engineer, title="Engineer's own")
        body = incidents_client.get(P, headers=actors.engineer).json()
        assert [i["title"] for i in body["items"]] == ["Theirs, assigned"]
        assert body["total"] == 1

    def test_an_admin_sees_everything(
        self, incidents_client: TestClient, actors: Actors, seeded: dict[str, Any]
    ) -> None:
        assert incidents_client.get(P, headers=actors.admin).json()["total"] == 3

    def test_every_row_carries_its_target_and_where_it_stands(
        self, incidents_client: TestClient, actors: Actors, seeded: dict[str, Any]
    ) -> None:
        """`due_at` is creation plus the D8 target; a fresh incident is on track."""
        body = incidents_client.get(P, headers=actors.admin).json()
        rows = {i["title"]: i for i in body["items"]}
        mine = rows["Mine"]
        created = dt.datetime.fromisoformat(mine["created_at"])
        assert dt.datetime.fromisoformat(mine["due_at"]) == created + dt.timedelta(days=7)
        assert mine["sla_state"] == "on_track"
        theirs = rows["Theirs"]
        assert dt.datetime.fromisoformat(theirs["due_at"]) == dt.datetime.fromisoformat(
            theirs["created_at"]
        ) + dt.timedelta(hours=4)

    def test_overdue_is_open_work_past_its_target(
        self,
        incidents_client: TestClient,
        db_session: Session,
        api: Api,
        actors: Actors,
        world: World,
        seeded: dict[str, Any],
    ) -> None:
        """Backdating puts a Critical past 4 h; resolving it takes it out of overdue.

        The filter and the per-row state must agree, since one is judged by
        the database clock and the other by the process clock.
        """
        now = dt.datetime.now(dt.UTC)
        backdate(db_session, seeded["theirs"]["id"], created_at=now - dt.timedelta(hours=5))
        late = api.moved(
            actors.admin,
            api.report(actors.employee, title="Late but done", priority="Critical")["id"],
            "In Progress",
            assignee_id=str(world.engineer.id),
        )
        api.moved(actors.engineer, late["id"], "Resolved", resolution_note="Fixed")
        backdate(db_session, late["id"], created_at=now - dt.timedelta(hours=6))

        overdue = incidents_client.get(P, params={"overdue": "true"}, headers=actors.admin).json()
        assert [i["title"] for i in overdue["items"]] == ["Theirs"]
        assert overdue["items"][0]["sla_state"] == "breached"
        rest = incidents_client.get(P, params={"overdue": "false"}, headers=actors.admin).json()
        assert sorted(i["title"] for i in rest["items"]) == [
            "Late but done",
            "Mine",
            "Theirs, assigned",
        ]
        states = {i["title"]: i["sla_state"] for i in rest["items"]}
        assert states["Late but done"] == "missed"
        assert states["Theirs, assigned"] == "on_track"

    def test_sort_by_due_orders_by_target_not_by_age(
        self, incidents_client: TestClient, actors: Actors, seeded: dict[str, Any]
    ) -> None:
        """A Critical reported last is due first; a Low reported first is due last."""
        body = incidents_client.get(
            P, params={"sort": "due_at", "order": "asc"}, headers=actors.admin
        ).json()
        assert [i["title"] for i in body["items"]] == ["Theirs", "Theirs, assigned", "Mine"]

    def test_a_filter_cannot_widen_scope(
        self, incidents_client: TestClient, actors: Actors, world: World, seeded: dict[str, Any]
    ) -> None:
        body = incidents_client.get(
            P, params={"assignee_id": str(world.engineer.id)}, headers=actors.employee
        ).json()
        assert body["items"] == [] and body["total"] == 0

    @pytest.mark.parametrize(
        ("params", "expected"),
        [
            ({"status": "In Progress"}, ["Theirs, assigned"]),
            ({"priority": "Critical"}, ["Theirs"]),
            ({"search": "assigned"}, ["Theirs, assigned"]),
            ({"search": "THEIRS"}, ["Theirs, assigned", "Theirs"]),
        ],
    )
    def test_filters(
        self, incidents_client: TestClient, actors: Actors, seeded: dict[str, Any],
        params: dict[str, str], expected: list[str],
    ) -> None:
        body = incidents_client.get(P, params=params, headers=actors.admin).json()
        # A set: rows created in one test transaction tie on created_at.
        assert {i["title"] for i in body["items"]} == set(expected)

    def test_filters_by_building_category_and_assignee(
        self, incidents_client: TestClient, api: Api, actors: Actors, world: World,
        seeded: dict[str, Any],
    ) -> None:
        api.report(actors.employee, title="Categorised", category_id=str(world.category.id))
        by_category = incidents_client.get(
            P, params={"category_id": str(world.category.id)}, headers=actors.admin
        ).json()
        assert [i["title"] for i in by_category["items"]] == ["Categorised"]
        by_assignee = incidents_client.get(
            P, params={"assignee_id": str(world.engineer.id)}, headers=actors.admin
        ).json()
        assert [i["title"] for i in by_assignee["items"]] == ["Theirs, assigned"]
        by_building = incidents_client.get(
            P, params={"building_id": str(world.inactive_building.id)}, headers=actors.admin
        ).json()
        assert by_building["total"] == 0

    def test_filters_by_creation_date(
        self, incidents_client: TestClient, api: Api, actors: Actors, db_session: Session,
        seeded: dict[str, Any],
    ) -> None:
        today = dt.datetime.now(dt.UTC).date()
        old = api.report(actors.employee, title="Last month")
        backdate(db_session, old["id"], created_at=dt.datetime.now(dt.UTC) - dt.timedelta(days=40))
        week = {
            "created_from": (today - dt.timedelta(days=6)).isoformat(),
            "created_to": today.isoformat(),
        }
        recent = incidents_client.get(P, params=week, headers=actors.admin).json()
        assert "Last month" not in {i["title"] for i in recent["items"]}
        assert recent["total"] == 3
        before = incidents_client.get(
            P, params={"created_to": (today - dt.timedelta(days=7)).isoformat()},
            headers=actors.admin,
        ).json()
        assert [i["title"] for i in before["items"]] == ["Last month"]
        inverted = incidents_client.get(
            P, params={"created_from": today.isoformat(), "created_to": "2020-01-01"},
            headers=actors.admin,
        )
        assert inverted.status_code == 400

    def test_search_escapes_wildcards(
        self, incidents_client: TestClient, api: Api, actors: Actors, seeded: dict[str, Any]
    ) -> None:
        api.report(actors.employee, title="100% broken")
        body = incidents_client.get(P, params={"search": "%"}, headers=actors.admin).json()
        assert [i["title"] for i in body["items"]] == ["100% broken"]

    def test_sorts_priority_by_urgency_not_alphabet(
        self, incidents_client: TestClient, actors: Actors, seeded: dict[str, Any]
    ) -> None:
        body = incidents_client.get(
            P, params={"sort": "priority", "order": "asc"}, headers=actors.admin
        ).json()
        assert [i["priority"] for i in body["items"]] == ["Low", "High", "Critical"]

    def test_sorts_by_title_and_status(
        self, incidents_client: TestClient, actors: Actors, seeded: dict[str, Any]
    ) -> None:
        by_title = incidents_client.get(
            P, params={"sort": "title", "order": "asc"}, headers=actors.admin
        ).json()
        assert [i["title"] for i in by_title["items"]] == ["Mine", "Theirs", "Theirs, assigned"]
        by_status = incidents_client.get(
            P, params={"sort": "status", "order": "desc"}, headers=actors.admin
        ).json()
        assert by_status["items"][0]["status"] == "In Progress"

    @pytest.mark.parametrize("params", [{"sort": "reporter_id"}, {"order": "sideways"},
                                        {"limit": 0}, {"limit": 101}, {"offset": -1},
                                        {"bogus": "1"}])
    def test_rejects_anything_off_the_allowlist(
        self, incidents_client: TestClient, actors: Actors, params: dict[str, Any]
    ) -> None:
        resp = incidents_client.get(P, params=params, headers=actors.admin)
        assert resp.status_code == 400
        assert resp.json()["error"] == "validation_error"

    def test_pages_with_a_scoped_total(
        self, incidents_client: TestClient, actors: Actors, seeded: dict[str, Any]
    ) -> None:
        first = incidents_client.get(P, params={"limit": 2}, headers=actors.admin).json()
        second = incidents_client.get(
            P, params={"limit": 2, "offset": 2}, headers=actors.admin
        ).json()
        assert (len(first["items"]), first["total"], first["limit"]) == (2, 3, 2)
        assert (len(second["items"]), second["offset"]) == (1, 2)
        ids = {i["id"] for i in first["items"]} | {i["id"] for i in second["items"]}
        assert len(ids) == 3

    def test_default_order_is_newest_first(
        self, incidents_client: TestClient, actors: Actors, seeded: dict[str, Any]
    ) -> None:
        body = incidents_client.get(P, headers=actors.admin).json()
        stamps = [i["created_at"] for i in body["items"]]
        assert stamps == sorted(stamps, reverse=True)


# --------------------------------------------------------------------------- get


class TestGet:
    def test_the_404_200_pair_on_the_same_id(
        self, incidents_client: TestClient, api: Api, actors: Actors
    ) -> None:
        """T61 at the HTTP layer: one id, one caller sees it, one does not."""
        theirs = api.report(actors.other_employee)
        hidden = incidents_client.get(f"{P}/{theirs['id']}", headers=actors.employee)
        assert hidden.status_code == 404
        assert hidden.json()["error"] == "not_found"
        assert incidents_client.get(f"{P}/{theirs['id']}", headers=actors.admin).status_code == 200

    def test_a_nonexistent_id_is_indistinguishable(
        self, incidents_client: TestClient, api: Api, actors: Actors
    ) -> None:
        theirs = api.report(actors.other_employee)
        hidden = incidents_client.get(f"{P}/{theirs['id']}", headers=actors.employee).json()
        missing = incidents_client.get(f"{P}/{uuid.uuid4()}", headers=actors.employee).json()
        hidden.pop("request_id"), missing.pop("request_id")
        assert hidden == missing

    def test_a_malformed_id_is_a_400(self, incidents_client: TestClient, actors: Actors) -> None:
        assert incidents_client.get(f"{P}/not-a-uuid", headers=actors.employee).status_code == 400

    def test_an_employee_has_no_moves_on_their_open_incident(
        self, incidents_client: TestClient, api: Api, actors: Actors
    ) -> None:
        mine = api.report(actors.employee)
        body = incidents_client.get(f"{P}/{mine['id']}", headers=actors.employee).json()
        assert body["allowed_transitions"] == []

    def test_an_admin_is_offered_both_open_edges_with_their_requirements(
        self, incidents_client: TestClient, api: Api, actors: Actors
    ) -> None:
        mine = api.report(actors.employee)
        body = incidents_client.get(f"{P}/{mine['id']}", headers=actors.admin).json()
        assert body["allowed_transitions"] == [
            {"to": "In Progress", "label": "Acknowledge and start work",
             "requires": ["assignee_id"]},
            {"to": "Closed", "label": "Close without work", "requires": ["resolution_note"]},
        ]

    def test_an_existing_assignee_is_not_asked_for_again(
        self, incidents_client: TestClient, api: Api, actors: Actors, world: World
    ) -> None:
        mine = api.report(actors.employee)
        incidents_client.put(
            f"{P}/{mine['id']}", json={"assignee_id": str(world.engineer.id)}, headers=actors.admin
        )
        body = incidents_client.get(f"{P}/{mine['id']}", headers=actors.engineer).json()
        assert body["allowed_transitions"] == [
            {"to": "In Progress", "label": "Acknowledge and start work", "requires": []}
        ]

    def test_the_assigned_engineer_sees_block_and_resolve(
        self, incidents_client: TestClient, api: Api, actors: Actors
    ) -> None:
        started = api.in_progress(actors)
        body = incidents_client.get(f"{P}/{started['id']}", headers=actors.engineer).json()
        assert [(t["to"], t["requires"]) for t in body["allowed_transitions"]] == [
            ("Blocked", ["blocked_reason"]),
            ("Resolved", ["resolution_note"]),
        ]

    def test_the_reporter_may_close_or_reopen_a_resolved_incident(
        self, incidents_client: TestClient, api: Api, actors: Actors
    ) -> None:
        done = api.resolved(actors)
        body = incidents_client.get(f"{P}/{done['id']}", headers=actors.employee).json()
        assert [t["to"] for t in body["allowed_transitions"]] == ["Closed", "In Progress"]


# --------------------------------------------------------------------------- update


class TestUpdate:
    def test_the_reporter_edits_the_text_while_open(
        self, incidents_client: TestClient, api: Api, actors: Actors, world: World,
        verify_session: Session,
    ) -> None:
        mine = api.report(actors.employee)
        resp = incidents_client.put(
            f"{P}/{mine['id']}",
            json={"title": "Better title", "category_id": str(world.category.id)},
            headers=actors.employee,
        )
        assert resp.status_code == 200, resp.text
        row = stored(verify_session, mine["id"])
        assert (row.title, row.category_id) == ("Better title", world.category.id)

    def test_omitted_fields_are_unchanged_and_null_clears(
        self, incidents_client: TestClient, api: Api, actors: Actors, world: World
    ) -> None:
        mine = api.report(actors.employee, category_id=str(world.category.id))
        body = incidents_client.put(
            f"{P}/{mine['id']}", json={"category_id": None}, headers=actors.employee
        ).json()
        assert body["category_id"] is None and body["title"] == "Aircon dripping"

    def test_null_on_a_required_field_is_refused(
        self, incidents_client: TestClient, api: Api, actors: Actors
    ) -> None:
        mine = api.report(actors.employee)
        resp = incidents_client.put(f"{P}/{mine['id']}", json={"title": None}, headers=actors.admin)
        assert resp.status_code == 400

    def test_status_is_not_settable_here(
        self, incidents_client: TestClient, api: Api, actors: Actors
    ) -> None:
        mine = api.report(actors.employee)
        resp = incidents_client.put(
            f"{P}/{mine['id']}", json={"status": "Closed"}, headers=actors.admin
        )
        assert resp.status_code == 400

    @pytest.mark.parametrize("field", ["priority", "assignee_id"])
    def test_the_reporter_may_not_touch_priority_or_assignee(
        self, incidents_client: TestClient, api: Api, actors: Actors, world: World, field: str
    ) -> None:
        mine = api.report(actors.employee)
        value = "High" if field == "priority" else str(world.engineer.id)
        resp = incidents_client.put(
            f"{P}/{mine['id']}", json={"title": "ok", field: value}, headers=actors.employee
        )
        assert resp.status_code == 403
        assert resp.json()["error"] == "forbidden"
        # Whole request rejected: the permitted title change did not apply either.
        current = incidents_client.get(f"{P}/{mine['id']}", headers=actors.employee).json()
        assert current["title"] == "Aircon dripping"

    def test_the_reporter_may_not_edit_once_work_started(
        self, incidents_client: TestClient, api: Api, actors: Actors
    ) -> None:
        started = api.in_progress(actors)
        resp = incidents_client.put(
            f"{P}/{started['id']}", json={"title": "late edit"}, headers=actors.employee
        )
        assert resp.status_code == 403

    def test_the_assigned_engineer_may_not_edit_the_text(
        self, incidents_client: TestClient, api: Api, actors: Actors
    ) -> None:
        started = api.in_progress(actors)
        resp = incidents_client.put(
            f"{P}/{started['id']}", json={"title": "eng edit"}, headers=actors.engineer
        )
        assert resp.status_code == 403

    def test_an_outsider_gets_404_not_403(
        self, incidents_client: TestClient, api: Api, actors: Actors
    ) -> None:
        mine = api.report(actors.employee)
        resp = incidents_client.put(
            f"{P}/{mine['id']}", json={"title": "x"}, headers=actors.other_employee
        )
        assert resp.status_code == 404

    def test_an_admin_changes_priority_and_assignee(
        self, incidents_client: TestClient, api: Api, actors: Actors, world: World,
        verify_session: Session,
    ) -> None:
        mine = api.report(actors.employee)
        resp = incidents_client.put(
            f"{P}/{mine['id']}",
            json={"priority": "Critical", "assignee_id": str(world.engineer.id)},
            headers=actors.admin,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["assignee"]["id"] == str(world.engineer.id)
        row = stored(verify_session, mine["id"])
        assert (row.priority.value, row.assignee_id) == ("Critical", world.engineer.id)
        # Assigning without moving the status still leaves an audit row.
        rows = history_of(verify_session, mine["id"])
        assert [(r.from_status and r.from_status.value, r.to_status.value) for r in rows] == [
            (None, "Open"), ("Open", "Open")
        ]
        assert (rows[-1].actor_id, rows[-1].assignee_id) == (world.admin.id, world.engineer.id)

    @pytest.mark.parametrize("which", ["employee", "inactive_engineer", "nobody"])
    def test_the_assignee_must_be_an_active_engineer(
        self, incidents_client: TestClient, api: Api, actors: Actors, world: World, which: str
    ) -> None:
        mine = api.report(actors.employee)
        target = uuid.uuid4() if which == "nobody" else getattr(world, which).id
        resp = incidents_client.put(
            f"{P}/{mine['id']}", json={"assignee_id": str(target)}, headers=actors.admin
        )
        assert resp.status_code == 400
        assert resp.json()["details"][0]["field"] == "assignee_id"

    def test_unassigning_is_allowed_only_while_open(
        self, incidents_client: TestClient, api: Api, actors: Actors, world: World
    ) -> None:
        mine = api.report(actors.employee)
        incidents_client.put(
            f"{P}/{mine['id']}", json={"assignee_id": str(world.engineer.id)}, headers=actors.admin
        )
        assert incidents_client.put(
            f"{P}/{mine['id']}", json={"assignee_id": None}, headers=actors.admin
        ).status_code == 200
        started = api.in_progress(actors)
        resp = incidents_client.put(
            f"{P}/{started['id']}", json={"assignee_id": None}, headers=actors.admin
        )
        assert resp.status_code == 409

    def test_a_closed_incident_is_immutable(
        self, incidents_client: TestClient, api: Api, actors: Actors
    ) -> None:
        done = api.resolved(actors)
        api.moved(actors.employee, done["id"], "Closed")
        resp = incidents_client.put(f"{P}/{done['id']}", json={"title": "x"}, headers=actors.admin)
        assert resp.status_code == 409
        assert resp.json()["error"] == "conflict"

    def test_an_empty_body_is_a_no_op(
        self, incidents_client: TestClient, api: Api, actors: Actors
    ) -> None:
        mine = api.report(actors.employee)
        resp = incidents_client.put(f"{P}/{mine['id']}", json={}, headers=actors.employee)
        assert resp.status_code == 200


# --------------------------------------------------------------------------- delete


class TestDelete:
    @pytest.mark.parametrize("who", ["employee", "engineer"])
    def test_non_admins_are_forbidden_whether_or_not_it_exists(
        self, incidents_client: TestClient, api: Api, actors: Actors, who: str
    ) -> None:
        mine = api.report(actors.employee)
        headers = getattr(actors, who)
        assert incidents_client.delete(f"{P}/{mine['id']}", headers=headers).status_code == 403
        assert incidents_client.delete(f"{P}/{uuid.uuid4()}", headers=headers).status_code == 403

    def test_removes_the_incident_and_everything_beneath_it(
        self, incidents_client: TestClient, api: Api, actors: Actors, verify_session: Session
    ) -> None:
        started = api.in_progress(actors)
        incidents_client.post(
            f"{P}/{started['id']}/notes", json={"body": "note"}, headers=actors.employee
        )
        incidents_client.post(
            f"{P}/{started['id']}/escalations", json={"reason": "urgent"}, headers=actors.employee
        )
        resp = incidents_client.delete(f"{P}/{started['id']}", headers=actors.admin)
        assert resp.status_code == 204
        incident_id = uuid.UUID(started["id"])
        for table in (Incident, IncidentNote, IncidentStatusHistory, EscalationRequest):
            column = table.id if table is Incident else table.incident_id
            count = verify_session.execute(
                select(func.count()).select_from(table).where(column == incident_id)
            ).scalar_one()
            assert count == 0, table.__tablename__

    def test_a_missing_id_is_404(self, incidents_client: TestClient, actors: Actors) -> None:
        resp = incidents_client.delete(f"{P}/{uuid.uuid4()}", headers=actors.admin)
        assert resp.status_code == 404


# --------------------------------------------------------------------------- transition


class TestTransitionOrderOfChecks:
    """api.md I6: scope, edge, actor, fields, assignee -- the first failure wins."""

    def test_1_out_of_scope_is_404(self, api: Api, actors: Actors) -> None:
        theirs = api.report(actors.other_employee)
        assert api.move(actors.employee, theirs["id"], "In Progress").status_code == 404

    @pytest.mark.parametrize("target", ["Resolved", "Blocked", "Open"])
    def test_2_no_edge_is_409_even_for_an_admin(
        self, api: Api, actors: Actors, target: str
    ) -> None:
        mine = api.report(actors.employee)
        resp = api.move(actors.admin, mine["id"], target, resolution_note="n", blocked_reason="b")
        assert resp.status_code == 409
        assert resp.json()["error"] == "invalid_transition"

    @pytest.mark.parametrize("target", ["Open", "In Progress", "Resolved", "Blocked"])
    def test_2_nothing_leaves_closed(self, api: Api, actors: Actors, target: str) -> None:
        done = api.resolved(actors)
        api.moved(actors.admin, done["id"], "Closed")
        engineer = actors._world.engineer
        resp = api.move(actors.admin, done["id"], target, assignee_id=str(engineer.id))
        assert (resp.status_code, resp.json()["error"]) == (409, "invalid_transition")

    def test_3_wrong_actor_is_403_before_fields_are_checked(
        self, api: Api, actors: Actors
    ) -> None:
        """The employee omits the note too; the actor check fires first."""
        started = api.in_progress(actors)
        resp = api.move(actors.employee, started["id"], "Resolved")
        assert (resp.status_code, resp.json()["error"]) == (403, "forbidden")

    def test_3_an_unassigned_engineer_may_not_block(
        self, api: Api, actors: Actors
    ) -> None:
        """The other engineer cannot even see it: 404, not 403 (scoping first)."""
        started = api.in_progress(actors)
        resp = api.move(actors.other_engineer, started["id"], "Blocked", blocked_reason="x")
        assert resp.status_code == 404

    def test_3_only_the_reporter_or_admin_closes(
        self, api: Api, actors: Actors
    ) -> None:
        done = api.resolved(actors)
        resp = api.move(actors.engineer, done["id"], "Closed")
        assert resp.status_code == 403

    @pytest.mark.parametrize("note", [None, "", "   "])
    def test_4_a_required_note_must_be_present_and_non_blank(
        self, api: Api, actors: Actors, note: str | None
    ) -> None:
        started = api.in_progress(actors)
        fields = {} if note is None else {"resolution_note": note}
        resp = api.move(actors.engineer, started["id"], "Resolved", **fields)
        assert resp.status_code == 400
        assert resp.json()["details"] == [
            {"field": "resolution_note", "message": "This value is required."}
        ]

    def test_4_starting_work_needs_an_assignee(self, api: Api, actors: Actors) -> None:
        mine = api.report(actors.employee)
        resp = api.move(actors.admin, mine["id"], "In Progress")
        assert resp.status_code == 400
        assert resp.json()["details"][0]["field"] == "assignee_id"

    @pytest.mark.parametrize("whom", ["engineer", "other_engineer"])
    def test_5_an_engineer_may_not_assign_anyone(
        self, api: Api, actors: Actors, world: World, incidents_client: TestClient, whom: str
    ) -> None:
        """Not even themselves: assignment is an admin's act, full stop."""
        mine = api.report(actors.employee)
        incidents_client.put(
            f"{P}/{mine['id']}", json={"assignee_id": str(world.engineer.id)}, headers=actors.admin
        )
        resp = api.move(actors.engineer, mine["id"], "In Progress",
                        assignee_id=str(getattr(world, whom).id))
        assert (resp.status_code, resp.json()["error"]) == (403, "forbidden")

    def test_5_the_assignee_must_be_an_active_engineer(
        self, api: Api, actors: Actors, world: World
    ) -> None:
        mine = api.report(actors.employee)
        resp = api.move(actors.admin, mine["id"], "In Progress",
                        assignee_id=str(world.inactive_engineer.id))
        assert resp.status_code == 400
        assert resp.json()["details"][0]["field"] == "assignee_id"

    def test_5_an_employee_may_not_reassign_on_reopen(
        self, api: Api, actors: Actors, world: World
    ) -> None:
        done = api.resolved(actors)
        resp = api.move(actors.employee, done["id"], "In Progress",
                        assignee_id=str(world.other_engineer.id))
        assert resp.status_code == 403

    def test_an_unknown_target_is_400(self, api: Api, actors: Actors) -> None:
        mine = api.report(actors.employee)
        assert api.move(actors.admin, mine["id"], "Done").status_code == 400


class TestTransitionEdges:
    """Every legal edge end to end, with the history row and the stamps it writes."""

    def test_open_to_in_progress_stamps_and_assigns(
        self, api: Api, actors: Actors, world: World, verify_session: Session
    ) -> None:
        before = dt.datetime.now(dt.UTC)
        started = api.in_progress(actors)
        row = stored(verify_session, started["id"])
        assert row.status.value == "In Progress" and row.assignee_id == world.engineer.id
        assert row.acknowledged_at is not None and row.acknowledged_at >= before
        assert row.assigned_at == row.acknowledged_at
        assert row.resolved_at is None and row.closed_at is None
        rows = history_of(verify_session, started["id"])
        assert [(r.from_status and r.from_status.value, r.to_status.value) for r in rows] == [
            (None, "Open"), ("Open", "In Progress")
        ]
        assert rows[-1].actor_id == world.admin.id and rows[-1].note is None
        # The row names who the admin handed it to.
        assert rows[-1].assignee_id == world.engineer.id

    def test_the_assigned_engineer_starts_work_themselves(
        self, api: Api, actors: Actors, world: World, incidents_client: TestClient
    ) -> None:
        mine = api.report(actors.employee)
        incidents_client.put(
            f"{P}/{mine['id']}", json={"assignee_id": str(world.engineer.id)}, headers=actors.admin
        )
        body = api.moved(actors.engineer, mine["id"], "In Progress")
        assert body["status"] == "In Progress"

    def test_an_engineer_cannot_pick_up_their_own_report(
        self, api: Api, actors: Actors, world: World, incidents_client: TestClient
    ) -> None:
        """Reporting it does not make it theirs: 404 until an admin assigns it."""
        own = api.report(actors.engineer)
        resp = api.move(actors.engineer, own["id"], "In Progress",
                        assignee_id=str(world.engineer.id))
        assert resp.status_code == 404
        incidents_client.put(
            f"{P}/{own['id']}", json={"assignee_id": str(world.engineer.id)}, headers=actors.admin
        )
        body = api.moved(actors.engineer, own["id"], "In Progress")
        assert body["status"] == "In Progress"

    def test_open_to_closed_without_work(
        self, api: Api, actors: Actors, verify_session: Session
    ) -> None:
        mine = api.report(actors.employee)
        body = api.moved(actors.admin, mine["id"], "Closed", resolution_note="Duplicate of #12")
        assert body["status"] == "Closed" and body["resolution_note"] == "Duplicate of #12"
        row = stored(verify_session, mine["id"])
        assert row.closed_at is not None and row.resolved_at is None
        assert history_of(verify_session, mine["id"])[-1].note == "Duplicate of #12"

    def test_block_and_unblock(
        self, api: Api, actors: Actors, verify_session: Session
    ) -> None:
        started = api.in_progress(actors)
        blocked = api.moved(
            actors.engineer, started["id"], "Blocked", blocked_reason="Parts on order"
        )
        assert blocked["status"] == "Blocked" and blocked["blocked_reason"] == "Parts on order"
        unblocked = api.moved(actors.engineer, started["id"], "In Progress")
        assert unblocked["status"] == "In Progress" and unblocked["blocked_reason"] is None
        notes = [r.note for r in history_of(verify_session, started["id"])]
        assert notes == [None, None, "Parts on order", None]

    def test_resolve_close_and_the_stamps(
        self, api: Api, actors: Actors, verify_session: Session
    ) -> None:
        done = api.resolved(actors)
        row = stored(verify_session, done["id"])
        assert row.resolved_at is not None and row.resolution_note == "Fixed."
        closed = api.moved(actors.employee, done["id"], "Closed")
        assert closed["status"] == "Closed"
        row = stored(verify_session, done["id"])
        assert row.closed_at is not None and row.closed_at >= row.resolved_at

    def test_reopen_keeps_first_stamps_and_re_resolve_overwrites_the_latest(
        self, api: Api, actors: Actors, verify_session: Session
    ) -> None:
        done = api.resolved(actors)
        first = stored(verify_session, done["id"])
        first_ack, first_resolved = first.acknowledged_at, first.resolved_at

        reopened = api.moved(actors.employee, done["id"], "In Progress")
        assert reopened["status"] == "In Progress"
        again = api.moved(actors.engineer, done["id"], "Resolved", resolution_note="Really fixed.")
        assert again["resolution_note"] == "Really fixed."
        row = stored(verify_session, done["id"])
        assert row.acknowledged_at == first_ack
        assert row.resolved_at is not None and row.resolved_at > first_resolved

    def test_an_admin_takes_engineer_edges_but_cannot_invent_one(
        self, api: Api, actors: Actors
    ) -> None:
        started = api.in_progress(actors)
        blocked = api.move(actors.admin, started["id"], "Blocked", blocked_reason="x")
        assert blocked.status_code == 200
        assert api.move(actors.admin, started["id"], "Closed").status_code == 409

    def test_the_admin_triage_journey(
        self, incidents_client: TestClient, api: Api, actors: Actors, world: World
    ) -> None:
        """Employee reports; the engineer cannot see it until the admin assigns it."""
        mine = api.report(actors.employee)
        assert incidents_client.get(f"{P}/{mine['id']}", headers=actors.engineer).status_code == 404

        incidents_client.put(
            f"{P}/{mine['id']}", json={"assignee_id": str(world.engineer.id)}, headers=actors.admin
        )
        visible = incidents_client.get(f"{P}/{mine['id']}", headers=actors.engineer)
        assert visible.status_code == 200
        assert [t["to"] for t in visible.json()["allowed_transitions"]] == ["In Progress"]

        api.moved(actors.engineer, mine["id"], "In Progress")
        api.moved(actors.engineer, mine["id"], "Resolved", resolution_note="Replaced pump.")
        final = api.moved(actors.employee, mine["id"], "Closed")
        assert final["status"] == "Closed"
        history = incidents_client.get(f"{P}/{mine['id']}/history", headers=actors.employee).json()
        # The admin's assignment is a row of its own, the status unchanged.
        assert [h["to_status"] for h in history["items"]] == [
            "Open", "Open", "In Progress", "Resolved", "Closed"
        ]
        assert [h["actor"]["role"] for h in history["items"]] == [
            "Employee", "Facility Admin", "Engineer", "Engineer", "Employee"
        ]
        assert [h["assignee"] and h["assignee"]["id"] for h in history["items"]] == [
            None, str(world.engineer.id), None, None, None
        ]


# --------------------------------------------------------------------------- workflow + history


class TestWorkflow:
    def test_serialises_the_whole_state_machine(
        self, incidents_client: TestClient, actors: Actors
    ) -> None:
        body = incidents_client.get(f"{P}/workflow", headers=actors.employee).json()
        assert body["statuses"] == ["Open", "In Progress", "Blocked", "Resolved", "Closed"]
        assert len(body["transitions"]) == 7
        first = body["transitions"][0]
        assert first == {
            "from": "Open", "to": "In Progress", "label": "Acknowledge and start work",
            "allowed_actors": ["admin", "assigned_engineer"], "requires": ["assignee_id"],
        }
        assert not any(t["from"] == "Closed" for t in body["transitions"])


class TestHistory:
    def test_reads_forwards_by_default_and_backwards_on_request(
        self, incidents_client: TestClient, api: Api, actors: Actors
    ) -> None:
        done = api.resolved(actors)
        asc = incidents_client.get(f"{P}/{done['id']}/history", headers=actors.employee).json()
        assert [h["to_status"] for h in asc["items"]] == ["Open", "In Progress", "Resolved"]
        assert asc["items"][-1]["note"] == "Fixed."
        desc = incidents_client.get(
            f"{P}/{done['id']}/history", params={"order": "desc"}, headers=actors.employee
        ).json()
        assert desc["items"][0]["to_status"] == "Resolved"

    def test_says_who_assigned_whom(
        self, incidents_client: TestClient, api: Api, actors: Actors, world: World
    ) -> None:
        """Each hand-over names the engineer; a re-save of the same one is silent."""
        mine = api.report(actors.employee)
        for engineer in (world.engineer, world.engineer, world.other_engineer):
            resp = incidents_client.put(
                f"{P}/{mine['id']}", json={"assignee_id": str(engineer.id)}, headers=actors.admin
            )
            assert resp.status_code == 200, resp.text
        started = api.moved(actors.admin, mine["id"], "In Progress")
        assert started["assignee"]["id"] == str(world.other_engineer.id)

        items = incidents_client.get(
            f"{P}/{mine['id']}/history", headers=actors.employee
        ).json()["items"]
        who = [
            (
                h["from_status"],
                h["to_status"],
                h["actor"]["id"],
                h["assignee"] and h["assignee"]["id"],
            )
            for h in items
        ]
        assert who == [
            (None, "Open", str(world.employee.id), None),
            ("Open", "Open", str(world.admin.id), str(world.engineer.id)),
            ("Open", "Open", str(world.admin.id), str(world.other_engineer.id)),
            # Already assigned, so starting work hands it to nobody new.
            ("Open", "In Progress", str(world.admin.id), None),
        ]
        assert items[1]["assignee"]["full_name"] == world.engineer.full_name
        assert items[1]["assignee_id"] == str(world.engineer.id)

    def test_is_scoped_like_its_parent(
        self, incidents_client: TestClient, api: Api, actors: Actors
    ) -> None:
        theirs = api.report(actors.other_employee)
        assert incidents_client.get(
            f"{P}/{theirs['id']}/history", headers=actors.employee
        ).status_code == 404

    def test_pages(self, incidents_client: TestClient, api: Api, actors: Actors) -> None:
        done = api.resolved(actors)
        page = incidents_client.get(
            f"{P}/{done['id']}/history", params={"limit": 1, "offset": 1}, headers=actors.admin
        ).json()
        assert (page["total"], len(page["items"]), page["items"][0]["to_status"]) == (
            3, 1, "In Progress"
        )


# --------------------------------------------------------------------------- notes


class TestNotes:
    def test_the_reporter_adds_a_public_note(
        self, incidents_client: TestClient, api: Api, actors: Actors, world: World
    ) -> None:
        mine = api.report(actors.employee)
        resp = incidents_client.post(
            f"{P}/{mine['id']}/notes", json={"body": "Still dripping"}, headers=actors.employee
        )
        assert resp.status_code == 201, resp.text
        assert resp.headers["Location"] == f"{P}/{mine['id']}/notes"
        body = resp.json()
        assert body["visibility"] == "public"
        assert body["author"]["id"] == str(world.employee.id)
        assert body["author_id"] == str(world.employee.id)

    def test_an_employee_asking_for_internal_is_refused_not_downgraded(
        self, incidents_client: TestClient, api: Api, actors: Actors, verify_session: Session
    ) -> None:
        mine = api.report(actors.employee)
        resp = incidents_client.post(
            f"{P}/{mine['id']}/notes", json={"body": "secret", "visibility": "internal"},
            headers=actors.employee,
        )
        assert resp.status_code == 403
        count = verify_session.execute(select(func.count()).select_from(IncidentNote)).scalar_one()
        assert count == 0

    def test_internal_notes_are_hidden_from_the_employee_and_shown_to_staff(
        self, incidents_client: TestClient, api: Api, actors: Actors
    ) -> None:
        started = api.in_progress(actors)
        for body, visibility in (("public one", "public"), ("internal one", "internal")):
            resp = incidents_client.post(
                f"{P}/{started['id']}/notes", json={"body": body, "visibility": visibility},
                headers=actors.engineer,
            )
            assert resp.status_code == 201, resp.text
        seen = incidents_client.get(f"{P}/{started['id']}/notes", headers=actors.employee).json()
        assert [n["body"] for n in seen["items"]] == ["public one"]
        assert seen["total"] == 1
        for who in ("engineer", "admin"):
            staff = incidents_client.get(
                f"{P}/{started['id']}/notes", headers=getattr(actors, who)
            ).json()
            assert [n["body"] for n in staff["items"]] == ["public one", "internal one"]

    def test_a_closed_incident_takes_no_notes(
        self, incidents_client: TestClient, api: Api, actors: Actors
    ) -> None:
        done = api.resolved(actors)
        api.moved(actors.employee, done["id"], "Closed")
        resp = incidents_client.post(
            f"{P}/{done['id']}/notes", json={"body": "late"}, headers=actors.admin
        )
        assert resp.status_code == 409

    def test_notes_are_scoped_like_their_parent(
        self, incidents_client: TestClient, api: Api, actors: Actors
    ) -> None:
        theirs = api.report(actors.other_employee)
        assert incidents_client.get(
            f"{P}/{theirs['id']}/notes", headers=actors.employee
        ).status_code == 404
        assert incidents_client.post(
            f"{P}/{theirs['id']}/notes", json={"body": "x"}, headers=actors.employee
        ).status_code == 404

    def test_a_blank_note_is_refused(
        self, incidents_client: TestClient, api: Api, actors: Actors
    ) -> None:
        mine = api.report(actors.employee)
        resp = incidents_client.post(
            f"{P}/{mine['id']}/notes", json={"body": "   "}, headers=actors.employee
        )
        assert resp.status_code == 400


# --------------------------------------------------------------------------- escalations


class TestEscalations:
    def test_the_reporter_requests_one(
        self, incidents_client: TestClient, api: Api, actors: Actors, world: World
    ) -> None:
        mine = api.report(actors.employee)
        resp = incidents_client.post(
            f"{P}/{mine['id']}/escalations", json={"reason": "Server room"}, headers=actors.employee
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["status"] == "Pending" and body["decided_by"] is None
        assert body["requested_by"]["id"] == str(world.employee.id)

    def test_the_assigned_engineer_requests_one(
        self, incidents_client: TestClient, api: Api, actors: Actors
    ) -> None:
        started = api.in_progress(actors)
        resp = incidents_client.post(
            f"{P}/{started['id']}/escalations", json={"reason": "Worse than reported"},
            headers=actors.engineer,
        )
        assert resp.status_code == 201, resp.text

    def test_an_admin_who_can_see_it_but_did_not_report_it_is_forbidden(
        self, incidents_client: TestClient, api: Api, actors: Actors
    ) -> None:
        mine = api.report(actors.employee)
        resp = incidents_client.post(
            f"{P}/{mine['id']}/escalations", json={"reason": "x"}, headers=actors.admin
        )
        assert resp.status_code == 403

    def test_an_outsider_gets_404(
        self, incidents_client: TestClient, api: Api, actors: Actors
    ) -> None:
        mine = api.report(actors.employee)
        resp = incidents_client.post(
            f"{P}/{mine['id']}/escalations", json={"reason": "x"}, headers=actors.other_engineer
        )
        assert resp.status_code == 404

    @pytest.mark.parametrize("state", ["Resolved", "Closed"])
    def test_finished_work_cannot_be_escalated(
        self, incidents_client: TestClient, api: Api, actors: Actors, state: str
    ) -> None:
        done = api.resolved(actors)
        if state == "Closed":
            api.moved(actors.employee, done["id"], "Closed")
        resp = incidents_client.post(
            f"{P}/{done['id']}/escalations", json={"reason": "x"}, headers=actors.employee
        )
        assert resp.status_code == 409

    def test_critical_cannot_go_higher(
        self, incidents_client: TestClient, api: Api, actors: Actors
    ) -> None:
        mine = api.report(actors.employee, priority="Critical")
        resp = incidents_client.post(
            f"{P}/{mine['id']}/escalations", json={"reason": "x"}, headers=actors.employee
        )
        assert resp.status_code == 409

    def test_one_pending_request_at_a_time(
        self, incidents_client: TestClient, api: Api, actors: Actors
    ) -> None:
        mine = api.report(actors.employee)
        url = f"{P}/{mine['id']}/escalations"
        first = incidents_client.post(url, json={"reason": "x"}, headers=actors.employee)
        second = incidents_client.post(url, json={"reason": "y"}, headers=actors.employee)
        assert (first.status_code, second.status_code) == (201, 409)

    def test_listing_for_an_incident_is_scoped(
        self, incidents_client: TestClient, api: Api, actors: Actors
    ) -> None:
        mine = api.report(actors.employee)
        incidents_client.post(
            f"{P}/{mine['id']}/escalations", json={"reason": "x"}, headers=actors.employee
        )
        own = incidents_client.get(f"{P}/{mine['id']}/escalations", headers=actors.employee).json()
        assert own["total"] == 1 and own["items"][0]["reason"] == "x"
        assert incidents_client.get(
            f"{P}/{mine['id']}/escalations", headers=actors.other_employee
        ).status_code == 404


class TestEscalationQueue:
    @pytest.fixture
    def pending(self, incidents_client: TestClient, api: Api, actors: Actors) -> list[str]:
        ids = []
        for title in ("first", "second"):
            incident = api.report(actors.employee, title=title, priority="Low")
            resp = incidents_client.post(
                f"{P}/{incident['id']}/escalations", json={"reason": title},
                headers=actors.employee,
            )
            ids.append(resp.json()["id"])
        return ids

    @pytest.mark.parametrize("who", ["employee", "engineer"])
    def test_the_queue_and_decisions_are_admin_only(
        self, incidents_client: TestClient, actors: Actors, pending: list[str], who: str
    ) -> None:
        headers = getattr(actors, who)
        assert incidents_client.get(f"{P}/escalations", headers=headers).status_code == 403
        resp = incidents_client.post(
            f"{P}/escalations/{pending[0]}/decision", json={"decision": "Approved"}, headers=headers
        )
        assert resp.status_code == 403

    def test_pending_oldest_first_by_default(
        self, incidents_client: TestClient, actors: Actors, pending: list[str]
    ) -> None:
        body = incidents_client.get(f"{P}/escalations", headers=actors.admin).json()
        assert [e["id"] for e in body["items"]] == pending
        assert body["total"] == 2

    def test_approval_raises_priority_one_level_and_stamps_the_decision(
        self, incidents_client: TestClient, actors: Actors, world: World, pending: list[str],
        verify_session: Session,
    ) -> None:
        resp = incidents_client.post(
            f"{P}/escalations/{pending[0]}/decision",
            json={"decision": "Approved", "decision_note": "Agreed"},
            headers=actors.admin,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "Approved" and body["decision_note"] == "Agreed"
        assert body["decided_by"]["id"] == str(world.admin.id) and body["decided_at"]
        escalation = verify_session.get(
            EscalationRequest, uuid.UUID(pending[0]), populate_existing=True
        )
        assert escalation is not None
        assert stored(verify_session, str(escalation.incident_id)).priority.value == "Medium"

    def test_rejection_leaves_priority_alone(
        self, incidents_client: TestClient, actors: Actors, pending: list[str],
        verify_session: Session,
    ) -> None:
        body = incidents_client.post(
            f"{P}/escalations/{pending[1]}/decision", json={"decision": "Rejected"},
            headers=actors.admin,
        ).json()
        assert body["status"] == "Rejected"
        assert stored(verify_session, body["incident_id"]).priority.value == "Low"

    def test_the_queue_filters_by_status(
        self, incidents_client: TestClient, actors: Actors, pending: list[str]
    ) -> None:
        incidents_client.post(
            f"{P}/escalations/{pending[0]}/decision", json={"decision": "Approved"},
            headers=actors.admin,
        )
        still_pending = incidents_client.get(f"{P}/escalations", headers=actors.admin).json()
        assert [e["id"] for e in still_pending["items"]] == [pending[1]]
        approved = incidents_client.get(
            f"{P}/escalations", params={"status": "Approved"}, headers=actors.admin
        ).json()
        assert [e["id"] for e in approved["items"]] == [pending[0]]

    def test_the_queue_can_span_every_status_when_asked_in_code(
        self, db_session: Session, actors: Actors, world: World, incidents_client: TestClient,
        pending: list[str],
    ) -> None:
        """No query string can clear the default; a future "all" view calls this directly."""
        from acme_core.schemas.incident import EscalationFilters
        from acme_core.security.principal import Principal
        from incidents_service import repository as repo

        incidents_client.post(
            f"{P}/escalations/{pending[0]}/decision", json={"decision": "Rejected"},
            headers=actors.admin,
        )
        rows, total = repo.list_escalations(
            db_session, Principal.from_user(world.admin), EscalationFilters(status=None)
        )
        assert total == 2 and {r.status.value for r in rows} == {"Pending", "Rejected"}

    def test_deciding_twice_is_409(
        self, incidents_client: TestClient, actors: Actors, pending: list[str]
    ) -> None:
        url = f"{P}/escalations/{pending[0]}/decision"
        incidents_client.post(url, json={"decision": "Rejected"}, headers=actors.admin)
        resp = incidents_client.post(url, json={"decision": "Approved"}, headers=actors.admin)
        assert resp.status_code == 409

    def test_pending_is_not_a_decision(
        self, incidents_client: TestClient, actors: Actors, pending: list[str]
    ) -> None:
        resp = incidents_client.post(
            f"{P}/escalations/{pending[0]}/decision", json={"decision": "Pending"},
            headers=actors.admin,
        )
        assert resp.status_code == 400

    def test_an_unknown_escalation_is_404(
        self, incidents_client: TestClient, actors: Actors
    ) -> None:
        resp = incidents_client.post(
            f"{P}/escalations/{uuid.uuid4()}/decision", json={"decision": "Approved"},
            headers=actors.admin,
        )
        assert resp.status_code == 404

    def test_a_second_approval_cannot_pass_critical(
        self, incidents_client: TestClient, api: Api, actors: Actors, verify_session: Session
    ) -> None:
        """Approve at High -> Critical, then a request made before that lands on Critical."""
        incident = api.report(actors.employee, priority="High")
        first = incidents_client.post(
            f"{P}/{incident['id']}/escalations", json={"reason": "a"}, headers=actors.employee
        ).json()
        incidents_client.post(
            f"{P}/escalations/{first['id']}/decision", json={"decision": "Approved"},
            headers=actors.admin,
        )
        assert stored(verify_session, incident["id"]).priority.value == "Critical"


# --------------------------------------------------------------------------- reports


def backdate(session: Session, incident_id: str, **stamps: dt.datetime) -> None:
    """Rewrite stamped timestamps directly; the API never lets a client do this."""
    session.execute(update(Incident).where(Incident.id == uuid.UUID(incident_id)).values(**stamps))
    session.commit()


class TestReports:
    @pytest.mark.parametrize("path", ["summary", "sla", "volume", "buildings", "engineers"])
    @pytest.mark.parametrize("who", ["employee", "engineer"])
    def test_admin_only(
        self, incidents_client: TestClient, actors: Actors, path: str, who: str
    ) -> None:
        resp = incidents_client.get(f"{P}/reports/{path}", headers=getattr(actors, who))
        assert resp.status_code == 403

    @pytest.mark.parametrize(
        "params",
        [
            {"from": "2026-09-10", "to": "2026-09-01"},
            {"from": "2025-01-01", "to": "2026-01-02"},
            {"group_by": "reporter"},
            {"interval": "hour"},
            {"bogus": "1"},
        ],
    )
    def test_bad_parameters_are_400(
        self, incidents_client: TestClient, actors: Actors, params: dict[str, str]
    ) -> None:
        path = "volume" if "interval" in params else "sla"
        resp = incidents_client.get(f"{P}/reports/{path}", params=params, headers=actors.admin)
        assert resp.status_code == 400

    def test_summary_counts_and_backlog_age(
        self, incidents_client: TestClient, api: Api, actors: Actors, db_session: Session
    ) -> None:
        now = dt.datetime.now(dt.UTC)
        fresh = api.report(actors.employee, priority="High")
        old = api.report(actors.employee, priority="Low")
        backdate(db_session, old["id"], created_at=now - dt.timedelta(days=5))
        done = api.resolved(actors)
        api.moved(actors.employee, done["id"], "Closed")

        body = incidents_client.get(f"{P}/reports/summary", headers=actors.admin).json()
        assert body["total"] == 3
        assert body["from"] and body["to"] == now.date().isoformat()
        assert body["by_status"] == [
            {"key": "Open", "count": 2}, {"key": "In Progress", "count": 0},
            {"key": "Blocked", "count": 0}, {"key": "Resolved", "count": 0},
            {"key": "Closed", "count": 1},
        ]
        assert {b["key"]: b["count"] for b in body["by_priority"]} == {
            "Low": 1, "Medium": 1, "High": 1, "Critical": 0
        }
        assert body["backlog_by_age"] == [
            {"key": "<1d", "count": 1}, {"key": "1-3d", "count": 0},
            {"key": "3-7d", "count": 1}, {"key": ">7d", "count": 0},
        ]
        assert fresh["id"]  # created inside the window

    def test_the_window_and_building_filter_apply(
        self, incidents_client: TestClient, api: Api, actors: Actors, db_session: Session,
        world: World,
    ) -> None:
        now = dt.datetime.now(dt.UTC)
        ancient = api.report(actors.employee)
        backdate(db_session, ancient["id"], created_at=now - dt.timedelta(days=60))
        api.report(actors.employee)
        default = incidents_client.get(f"{P}/reports/summary", headers=actors.admin).json()
        assert default["total"] == 1
        wide = incidents_client.get(
            f"{P}/reports/summary",
            params={"from": (now - dt.timedelta(days=90)).date().isoformat()},
            headers=actors.admin,
        ).json()
        assert wide["total"] == 2
        elsewhere = incidents_client.get(
            f"{P}/reports/summary", params={"building_id": str(world.inactive_building.id)},
            headers=actors.admin,
        ).json()
        assert elsewhere["total"] == 0

    def test_sla_by_priority(
        self, incidents_client: TestClient, api: Api, actors: Actors, db_session: Session
    ) -> None:
        now = dt.datetime.now(dt.UTC)
        # Critical, resolved in 6 h: outside its 4 h target.
        late = api.report(actors.employee, priority="Critical")
        backdate(db_session, late["id"], created_at=now - dt.timedelta(hours=6))
        engineer_id = str(actors._world.engineer.id)
        api.moved(actors.admin, late["id"], "In Progress", assignee_id=engineer_id)
        api.moved(actors.engineer, late["id"], "Resolved", resolution_note="slow")
        # Low, resolved in 1 h: well inside 7 d.
        quick = api.report(actors.employee, priority="Low")
        backdate(db_session, quick["id"], created_at=now - dt.timedelta(hours=1))
        api.moved(actors.admin, quick["id"], "In Progress", assignee_id=engineer_id)
        api.moved(actors.engineer, quick["id"], "Resolved", resolution_note="fast")
        # Low, never touched: counted, contributes nothing to durations.
        api.report(actors.employee, priority="Low")

        body = incidents_client.get(f"{P}/reports/sla", headers=actors.admin).json()
        assert body["group_by"] == "priority"
        assert {t["priority"]: t["target_seconds"] for t in body["targets"]} == {
            p.value: int(d.total_seconds()) for p, d in SLA_TARGETS.items()
        }
        rows = {r["group"]: r for r in body["rows"]}
        assert set(rows) == {"Critical", "Low"}
        critical, low = rows["Critical"], rows["Low"]
        assert (critical["count"], critical["resolved_count"]) == (1, 1)
        assert critical["within_target_ratio"] == 0.0
        assert 6 * 3600 <= critical["mean_resolve_seconds"] < 6 * 3600 + 60
        assert critical["p90_ack_seconds"] == pytest.approx(critical["mean_ack_seconds"])
        assert (low["count"], low["resolved_count"], low["within_target_ratio"]) == (2, 1, 1.0)
        assert 3600 <= low["p90_resolve_seconds"] < 3660

    @pytest.mark.parametrize("group_by", ["building", "category"])
    def test_sla_by_building_and_category(
        self, incidents_client: TestClient, api: Api, actors: Actors, world: World, group_by: str
    ) -> None:
        api.report(actors.employee, category_id=str(world.category.id))
        api.report(actors.employee)
        body = incidents_client.get(
            f"{P}/reports/sla", params={"group_by": group_by}, headers=actors.admin
        ).json()
        rows = {r["group"]: r for r in body["rows"]}
        if group_by == "building":
            assert rows == {"Headquarters": {
                "group": "Headquarters", "count": 2, "resolved_count": 0,
                "mean_ack_seconds": None, "p90_ack_seconds": None,
                "mean_resolve_seconds": None, "p90_resolve_seconds": None,
                "within_target_ratio": None,
            }}
        else:
            assert {g: r["count"] for g, r in rows.items()} == {"HVAC": 1, "Uncategorised": 1}

    def test_volume_per_day_and_week(
        self, incidents_client: TestClient, api: Api, actors: Actors, db_session: Session,
        world: World,
    ) -> None:
        today = dt.datetime.now(dt.UTC).replace(hour=12)
        api.report(actors.employee, priority="High")
        api.report(actors.employee, priority="High")
        earlier = api.report(actors.employee, category_id=str(world.category.id))
        backdate(db_session, earlier["id"], created_at=today - dt.timedelta(days=10))

        by_day = incidents_client.get(
            f"{P}/reports/volume", params={"group_by": "priority"}, headers=actors.admin
        ).json()
        assert by_day["interval"] == "day"
        assert by_day["rows"] == [
            {"bucket_start": (today - dt.timedelta(days=10)).date().isoformat(),
             "group": "Medium", "count": 1},
            {"bucket_start": today.date().isoformat(), "group": "High", "count": 2},
        ]
        by_week = incidents_client.get(
            f"{P}/reports/volume", params={"interval": "week", "group_by": "category"},
            headers=actors.admin,
        ).json()
        assert sum(r["count"] for r in by_week["rows"]) == 3
        assert {r["group"] for r in by_week["rows"]} == {"HVAC", "Uncategorised"}
        monday = (today - dt.timedelta(days=today.weekday())).date().isoformat()
        assert any(
            r["bucket_start"] == monday and r["group"] == "Uncategorised" for r in by_week["rows"]
        )
        by_status = incidents_client.get(
            f"{P}/reports/volume", params={"group_by": "status"}, headers=actors.admin
        ).json()
        assert {r["group"] for r in by_status["rows"]} == {"Open"}

    def test_buildings_busiest_first_with_quiet_active_ones(
        self, incidents_client: TestClient, api: Api, actors: Actors, db_session: Session,
        world: World,
    ) -> None:
        annex = Building(code="ANX", name="Annex")
        db_session.add(annex)
        db_session.commit()
        api.report(actors.employee, building_id=str(annex.id), priority="Critical")
        api.report(actors.employee, building_id=str(annex.id))
        hq = api.resolved(actors)
        api.moved(actors.employee, hq["id"], "Closed")

        body = incidents_client.get(f"{P}/reports/buildings", headers=actors.admin).json()
        assert body["rows"] == [
            {"building_id": str(annex.id), "building": "Annex",
             "count": 2, "open_count": 2, "critical_count": 1},
            {"building_id": str(world.building.id), "building": "Headquarters",
             "count": 1, "open_count": 0, "critical_count": 0},
        ]
        # The retired building has nothing in the window, so it is not listed.
        assert "Decommissioned" not in {r["building"] for r in body["rows"]}

        one = incidents_client.get(
            f"{P}/reports/buildings", params={"building_id": str(annex.id)},
            headers=actors.admin,
        ).json()
        assert [r["building"] for r in one["rows"]] == ["Annex"]

    def test_engineers_most_completed_first(
        self, incidents_client: TestClient, api: Api, actors: Actors, db_session: Session,
        world: World,
    ) -> None:
        now = dt.datetime.now(dt.UTC)
        # The engineer resolves two (one is then closed) and still holds one.
        first = api.resolved(actors)
        backdate(db_session, first["id"], created_at=now - dt.timedelta(hours=2))
        second = api.resolved(actors)
        api.moved(actors.employee, second["id"], "Closed")
        backdate(db_session, second["id"], created_at=now - dt.timedelta(hours=4))
        api.in_progress(actors)
        # The other engineer holds one, blocked.
        held = api.in_progress(actors, engineer=world.other_engineer)
        api.moved(actors.admin, held["id"], "Blocked", blocked_reason="Parts on order")
        # Closed without work: counts for nobody.
        untouched = api.report(actors.employee)
        api.moved(actors.admin, untouched["id"], "Closed", resolution_note="Duplicate")

        body = incidents_client.get(f"{P}/reports/engineers", headers=actors.admin).json()
        rows = body["rows"]
        assert [r["engineer_id"] for r in rows] == [
            str(world.engineer.id), str(world.other_engineer.id)
        ]
        lead, other = rows
        assert (lead["assigned_count"], lead["open_count"], lead["completed_count"]) == (3, 1, 2)
        assert lead["is_active"] is True
        assert lead["specialty"] == "HVAC"
        assert other["specialty"] == "General"
        assert 3 * 3600 <= lead["mean_resolve_seconds"] < 3 * 3600 + 60
        assert (other["assigned_count"], other["open_count"], other["completed_count"]) == (1, 1, 0)
        assert other["mean_resolve_seconds"] is None
        # Deactivated and holding nothing: not listed.
        assert str(world.inactive_engineer.id) not in {r["engineer_id"] for r in rows}

    def test_engineers_with_nothing_still_appear(
        self, incidents_client: TestClient, actors: Actors, world: World
    ) -> None:
        body = incidents_client.get(f"{P}/reports/engineers", headers=actors.admin).json()
        assert {r["engineer"] for r in body["rows"]} == {
            world.engineer.full_name, world.other_engineer.full_name
        }
        assert all(
            (r["assigned_count"], r["completed_count"], r["mean_resolve_seconds"]) == (0, 0, None)
            for r in body["rows"]
        )


# --------------------------------------------------------------------------- notifications


def notifications_of(session: Session, user: User) -> list[Notification]:
    return list(
        session.scalars(
            select(Notification)
            .where(Notification.user_id == user.id)
            .order_by(Notification.created_at, Notification.id)
        )
    )


class TestNotifications:
    """Admins hear about every report; an engineer hears when work lands on them."""

    def test_every_active_admin_is_told_about_a_report(
        self,
        api: Api,
        actors: Actors,
        world: World,
        make_user: Any,
        verify_session: Session,
    ) -> None:
        second_admin = make_user(Role.FACILITY_ADMIN, email="admin2@acme.inc")
        retired_admin = make_user(Role.FACILITY_ADMIN, email="gone@acme.inc", is_active=False)
        incident = api.report(actors.employee, title="Lift stuck")

        for admin in (world.admin, second_admin):
            rows = notifications_of(verify_session, admin)
            assert len(rows) == 1
            row = rows[0]
            assert row.kind.value == "Reported"
            assert str(row.incident_id) == incident["id"]
            assert row.incident_title == "Lift stuck"
            assert row.actor_id == world.employee.id
            assert row.read_at is None
        assert notifications_of(verify_session, retired_admin) == []
        # The reporter and the engineers hear nothing about a report.
        for bystander in (world.employee, world.engineer):
            assert notifications_of(verify_session, bystander) == []

    def test_an_admin_reporting_is_not_told_about_their_own(
        self, api: Api, actors: Actors, world: World, verify_session: Session
    ) -> None:
        api.report(actors.admin)
        assert notifications_of(verify_session, world.admin) == []

    def test_assigning_through_edit_tells_the_engineer(
        self,
        incidents_client: TestClient,
        api: Api,
        actors: Actors,
        world: World,
        verify_session: Session,
    ) -> None:
        incident = api.report(actors.employee)
        resp = incidents_client.put(
            f"{P}/{incident['id']}",
            json={"assignee_id": str(world.engineer.id)},
            headers=actors.admin,
        )
        assert resp.status_code == 200, resp.text

        rows = notifications_of(verify_session, world.engineer)
        assert [(r.kind.value, r.actor_id) for r in rows] == [("Assigned", world.admin.id)]
        assert str(rows[0].incident_id) == incident["id"]
        assert notifications_of(verify_session, world.other_engineer) == []

    def test_assigning_through_a_transition_tells_the_engineer(
        self, api: Api, actors: Actors, world: World, verify_session: Session
    ) -> None:
        incident = api.in_progress(actors)
        rows = notifications_of(verify_session, world.engineer)
        assert [r.kind.value for r in rows] == ["Assigned"]
        assert str(rows[0].incident_id) == incident["id"]

    def test_reassigning_tells_the_new_engineer_only(
        self,
        incidents_client: TestClient,
        api: Api,
        actors: Actors,
        world: World,
        verify_session: Session,
    ) -> None:
        incident = api.in_progress(actors)
        resp = incidents_client.put(
            f"{P}/{incident['id']}",
            json={"assignee_id": str(world.other_engineer.id)},
            headers=actors.admin,
        )
        assert resp.status_code == 200, resp.text
        assert len(notifications_of(verify_session, world.engineer)) == 1
        assert [r.kind.value for r in notifications_of(verify_session, world.other_engineer)] == [
            "Assigned"
        ]

    def test_saving_the_same_assignee_again_says_nothing_new(
        self,
        incidents_client: TestClient,
        api: Api,
        actors: Actors,
        world: World,
        verify_session: Session,
    ) -> None:
        incident = api.in_progress(actors)
        resp = incidents_client.put(
            f"{P}/{incident['id']}",
            json={"assignee_id": str(world.engineer.id), "priority": "High"},
            headers=actors.admin,
        )
        assert resp.status_code == 200, resp.text
        assert len(notifications_of(verify_session, world.engineer)) == 1

    def test_a_failed_assignment_leaves_no_notification(
        self,
        incidents_client: TestClient,
        api: Api,
        actors: Actors,
        world: World,
        verify_session: Session,
    ) -> None:
        incident = api.report(actors.employee)
        resp = incidents_client.put(
            f"{P}/{incident['id']}",
            json={"assignee_id": str(world.inactive_engineer.id)},
            headers=actors.admin,
        )
        assert resp.status_code == 400
        assert notifications_of(verify_session, world.inactive_engineer) == []

    # ---- reading them back

    def test_the_list_is_newest_first_with_the_unread_total(
        self, incidents_client: TestClient, api: Api, actors: Actors
    ) -> None:
        first = api.report(actors.employee, title="First")
        second = api.report(actors.employee, title="Second")

        body = incidents_client.get(f"{P}/notifications", headers=actors.admin).json()
        assert body["total"] == 2
        assert body["unread_count"] == 2
        assert [n["incident_title"] for n in body["items"]] == ["Second", "First"]
        assert [n["incident_id"] for n in body["items"]] == [second["id"], first["id"]]
        item = body["items"][0]
        assert item["kind"] == "Reported"
        assert item["read_at"] is None
        assert item["actor"]["full_name"] == "User 1"
        assert "email" not in item["actor"]

    def test_only_your_own_are_listed(
        self, incidents_client: TestClient, api: Api, actors: Actors
    ) -> None:
        api.in_progress(actors)
        engineer = incidents_client.get(f"{P}/notifications", headers=actors.engineer).json()
        other = incidents_client.get(f"{P}/notifications", headers=actors.other_engineer).json()
        employee = incidents_client.get(f"{P}/notifications", headers=actors.employee).json()
        assert [n["kind"] for n in engineer["items"]] == ["Assigned"]
        assert (other["total"], other["unread_count"]) == (0, 0)
        assert (employee["total"], employee["unread_count"]) == (0, 0)

    def test_marking_one_read(
        self, incidents_client: TestClient, api: Api, actors: Actors, verify_session: Session
    ) -> None:
        api.report(actors.employee)
        api.report(actors.employee)
        listed = incidents_client.get(f"{P}/notifications", headers=actors.admin).json()
        target = listed["items"][0]["id"]

        resp = incidents_client.post(f"{P}/notifications/{target}/read", headers=actors.admin)
        assert resp.status_code == 200, resp.text
        assert resp.json()["read_at"] is not None
        # Idempotent: reading it again keeps the first instant (the two
        # answers may render it in different zones, so compare parsed).
        again = incidents_client.post(f"{P}/notifications/{target}/read", headers=actors.admin)
        assert dt.datetime.fromisoformat(again.json()["read_at"]) == dt.datetime.fromisoformat(
            resp.json()["read_at"]
        )

        row = verify_session.get(Notification, uuid.UUID(target), populate_existing=True)
        assert row is not None and row.read_at is not None
        body = incidents_client.get(f"{P}/notifications", headers=actors.admin).json()
        assert (body["total"], body["unread_count"]) == (2, 1)
        unread = incidents_client.get(
            f"{P}/notifications", params={"unread": "true"}, headers=actors.admin
        ).json()
        assert [n["id"] for n in unread["items"]] == [listed["items"][1]["id"]]
        assert unread["total"] == 1

    def test_someone_elses_notification_is_404_not_403(
        self, incidents_client: TestClient, api: Api, actors: Actors
    ) -> None:
        api.report(actors.employee)
        target = incidents_client.get(f"{P}/notifications", headers=actors.admin).json()["items"][
            0
        ]["id"]
        for stranger in (actors.engineer, actors.employee):
            resp = incidents_client.post(f"{P}/notifications/{target}/read", headers=stranger)
            assert resp.status_code == 404, resp.text
        assert (
            incidents_client.post(f"{P}/notifications/{NIL}/read", headers=actors.admin).status_code
            == 404
        )

    def test_marking_all_read(
        self, incidents_client: TestClient, api: Api, actors: Actors, verify_session: Session
    ) -> None:
        api.report(actors.employee)
        api.report(actors.employee)
        api.in_progress(actors)  # the engineer's, untouched by the admin's read-all

        resp = incidents_client.post(f"{P}/notifications/read-all", headers=actors.admin)
        assert resp.status_code == 204
        body = incidents_client.get(f"{P}/notifications", headers=actors.admin).json()
        assert body["unread_count"] == 0
        assert all(n["read_at"] is not None for n in body["items"])
        engineer = incidents_client.get(f"{P}/notifications", headers=actors.engineer).json()
        assert engineer["unread_count"] == 1
        # Nothing to do is still a 204.
        assert (
            incidents_client.post(f"{P}/notifications/read-all", headers=actors.admin).status_code
            == 204
        )

    def test_deleting_the_incident_removes_its_notifications(
        self,
        incidents_client: TestClient,
        api: Api,
        actors: Actors,
        world: World,
        verify_session: Session,
    ) -> None:
        incident = api.in_progress(actors)
        assert len(notifications_of(verify_session, world.engineer)) == 1
        resp = incidents_client.delete(f"{P}/{incident['id']}", headers=actors.admin)
        assert resp.status_code == 204
        verify_session.expire_all()
        assert notifications_of(verify_session, world.engineer) == []
        assert notifications_of(verify_session, world.admin) == []
