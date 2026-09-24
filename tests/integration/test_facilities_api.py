"""The facilities service end to end: real routes, real rows, real tokens.

Sign-in goes through the auth service on the same test transaction, so every
request here carries a token the real login endpoint issued. Persistence is
asserted through `verify_session`, which has its own identity map, so a change
that never reached PostgreSQL cannot read as applied (hazard 3).

Coverage follows api.md §3 and the task list: every endpoint for every role,
the 404/200 pair on the same id for a retired record, the uniqueness rules
surfaced as 409 (T67, T68), and the referential-integrity rule that a refused
delete leaves every child row exactly where it was (T72).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from acme_core.models import (
    Building,
    Category,
    EngineerProfile,
    Floor,
    Incident,
    IncidentStatus,
    Role,
    Seat,
    User,
)

pytestmark = pytest.mark.integration

P = "/api/facilities"
NIL = "00000000-0000-0000-0000-000000000000"


def bearer(tokens: dict[str, Any]) -> dict[str, str]:
    return {"Authorization": f"Bearer {tokens['access_token']}"}


# --------------------------------------------------------------------------- world


@dataclass
class World:
    """Enough facilities and people to exercise every rule."""

    hq: Building
    old: Building  # retired
    ground: Floor  # hq, level 1
    second: Floor  # hq, level 2, no seats
    old_floor: Floor  # in the retired building
    seat: Seat  # ground 1-01
    retired_seat: Seat  # ground 1-02, inactive
    old_seat: Seat  # on old_floor
    facilities: Category  # root
    hvac: Category  # child of facilities
    retired_category: Category  # inactive root
    employee: User
    engineer: User
    other_engineer: User
    inactive_engineer: User
    demoted: User  # Employee role, but still carries an engineer profile
    admin: User


@pytest.fixture
def world(db_session: Session, make_user: Any) -> World:
    hq = Building(code="HQ", name="Headquarters", address="1 Main St")
    old = Building(code="OLD", name="Decommissioned", is_active=False)
    db_session.add_all([hq, old])
    db_session.flush()
    ground = Floor(building_id=hq.id, level=1, name="Ground")
    second = Floor(building_id=hq.id, level=2)
    old_floor = Floor(building_id=old.id, level=1)
    db_session.add_all([ground, second, old_floor])
    db_session.flush()
    seat = Seat(floor_id=ground.id, code="1-01", label="Window")
    retired_seat = Seat(floor_id=ground.id, code="1-02", is_active=False)
    old_seat = Seat(floor_id=old_floor.id, code="1-01")
    facilities = Category(name="Facilities")
    retired_category = Category(name="Retired", is_active=False)
    db_session.add_all([seat, retired_seat, old_seat, facilities, retired_category])
    db_session.flush()
    hvac = Category(name="HVAC", parent_id=facilities.id)
    db_session.add(hvac)
    db_session.commit()

    demoted = make_user(Role.ENGINEER, email="demoted@acme.inc", specialty="Plumbing")
    demoted.role = Role.EMPLOYEE
    demoted.occupation = "Clerk"
    db_session.commit()

    return World(
        hq=hq,
        old=old,
        ground=ground,
        second=second,
        old_floor=old_floor,
        seat=seat,
        retired_seat=retired_seat,
        old_seat=old_seat,
        facilities=facilities,
        hvac=hvac,
        retired_category=retired_category,
        employee=make_user(email="emp@acme.inc"),
        engineer=make_user(Role.ENGINEER, email="eng@acme.inc", full_name="Ada", specialty="HVAC"),
        other_engineer=make_user(
            Role.ENGINEER, email="other.eng@acme.inc", full_name="Bob", specialty="Electrical"
        ),
        inactive_engineer=make_user(
            Role.ENGINEER, email="gone.eng@acme.inc", is_active=False, specialty="HVAC"
        ),
        demoted=demoted,
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


@pytest.fixture
def make_incident(db_session: Session, world: World) -> Any:
    """A committed incident naming the given location, reported by the employee."""

    def _make(**fields: Any) -> Incident:
        fields.setdefault("building_id", world.hq.id)
        incident = Incident(
            title="Something broke",
            description="Details",
            reporter_id=world.employee.id,
            **fields,
        )
        db_session.add(incident)
        db_session.commit()
        return incident

    return _make


class Api:
    """Thin helpers over the facilities client that assert the happy path."""

    def __init__(self, client: TestClient, world: World) -> None:
        self.client = client
        self.world = world

    def _create(self, path: str, headers: dict[str, str], body: dict[str, Any]) -> dict[str, Any]:
        resp = self.client.post(f"{P}/{path}", json=body, headers=headers)
        assert resp.status_code == 201, resp.text
        return resp.json()

    def building(self, headers: dict[str, str], **overrides: Any) -> dict[str, Any]:
        return self._create("buildings", headers, {"code": "NEW", "name": "New wing", **overrides})

    def floor(self, headers: dict[str, str], **overrides: Any) -> dict[str, Any]:
        body = {"building_id": str(self.world.hq.id), "level": 3, **overrides}
        return self._create("floors", headers, body)

    def seat(self, headers: dict[str, str], **overrides: Any) -> dict[str, Any]:
        body = {"floor_id": str(self.world.ground.id), "code": "1-03", **overrides}
        return self._create("seats", headers, body)

    def category(self, headers: dict[str, str], **overrides: Any) -> dict[str, Any]:
        return self._create("categories", headers, {"name": "Workplace", **overrides})


@pytest.fixture
def api(facilities_client: TestClient, world: World) -> Api:
    return Api(facilities_client, world)


def count(session: Session, model: type, **where: Any) -> int:
    statement = select(func.count()).select_from(model)
    for column, value in where.items():
        statement = statement.where(getattr(model, column) == value)
    return session.execute(statement).scalar_one()


def stored(session: Session, model: type, row_id: Any) -> Any:
    return session.get(model, uuid.UUID(str(row_id)), populate_existing=True)


# --------------------------------------------------------------------------- contract


class TestRouteContract:
    PUBLIC = {("GET", f"{P}/healthz"), ("GET", f"{P}/readyz")}
    PROTECTED_ROUTES = 23

    def test_every_other_route_rejects_an_anonymous_caller(
        self, facilities_client: TestClient
    ) -> None:
        schema = facilities_client.get(f"{P}/openapi.json").json()
        checked = 0
        for path, operations in schema["paths"].items():
            for method in operations:
                if (method.upper(), path) in self.PUBLIC:
                    continue
                url = path
                for param in ("building_id", "floor_id", "seat_id", "category_id", "user_id"):
                    url = url.replace("{" + param + "}", NIL)
                resp = facilities_client.request(method.upper(), url, json={})
                assert resp.status_code == 401, f"{method.upper()} {path} -> {resp.status_code}"
                checked += 1
        assert checked == self.PROTECTED_ROUTES, (
            "the protected-route count changed; update this test deliberately"
        )

    @pytest.mark.parametrize("method", ["post", "put", "delete"])
    def test_a_write_by_a_non_admin_is_refused_before_any_lookup(
        self, facilities_client: TestClient, actors: Actors, method: str
    ) -> None:
        """The role gate answers 403 whether or not the id exists."""
        url = f"{P}/buildings" if method == "post" else f"{P}/buildings/{uuid.uuid4()}"
        body = {"code": "X", "name": "X"} if method != "delete" else None
        for headers in (actors.employee, actors.engineer):
            resp = facilities_client.request(method.upper(), url, json=body, headers=headers)
            assert (resp.status_code, resp.json()["error"]) == (403, "forbidden")


# --------------------------------------------------------------------------- buildings


class TestBuildingList:
    def test_non_admins_see_active_buildings_in_code_order(
        self, facilities_client: TestClient, actors: Actors, api: Api
    ) -> None:
        api.building(actors.admin, code="ANNEX", name="Annex")
        page = facilities_client.get(f"{P}/buildings", headers=actors.employee).json()
        assert [b["code"] for b in page["items"]] == ["ANNEX", "HQ"]
        assert (page["total"], page["limit"], page["offset"]) == (2, 25, 0)

    def test_include_inactive_is_honoured_for_admins_only(
        self, facilities_client: TestClient, actors: Actors
    ) -> None:
        params = {"include_inactive": "true"}
        mine = facilities_client.get(f"{P}/buildings", params=params, headers=actors.employee)
        theirs = facilities_client.get(f"{P}/buildings", params=params, headers=actors.admin)
        assert [b["code"] for b in mine.json()["items"]] == ["HQ"]
        assert mine.json()["total"] == 1
        assert [b["code"] for b in theirs.json()["items"]] == ["HQ", "OLD"]
        assert theirs.json()["total"] == 2

    def test_admins_see_active_only_by_default(
        self, facilities_client: TestClient, actors: Actors
    ) -> None:
        page = facilities_client.get(f"{P}/buildings", headers=actors.admin).json()
        assert [b["code"] for b in page["items"]] == ["HQ"]

    def test_search_matches_code_or_name_with_wildcards_escaped(
        self, facilities_client: TestClient, actors: Actors, api: Api
    ) -> None:
        api.building(actors.admin, code="A%B", name="Percent")
        api.building(actors.admin, code="AB", name="Plain")
        by_name = facilities_client.get(
            f"{P}/buildings", params={"search": "quart"}, headers=actors.employee
        ).json()
        assert [b["code"] for b in by_name["items"]] == ["HQ"]
        literal = facilities_client.get(
            f"{P}/buildings", params={"search": "%"}, headers=actors.employee
        ).json()
        assert [b["code"] for b in literal["items"]] == ["A%B"]

    def test_sort_is_an_allowlist(self, facilities_client: TestClient, actors: Actors) -> None:
        resp = facilities_client.get(
            f"{P}/buildings", params={"sort": "id"}, headers=actors.employee
        )
        assert (resp.status_code, resp.json()["error"]) == (400, "validation_error")

    def test_sorting_by_name_descending_with_paging(
        self, facilities_client: TestClient, actors: Actors, api: Api
    ) -> None:
        api.building(actors.admin, code="ANNEX", name="Annex")
        page = facilities_client.get(
            f"{P}/buildings",
            params={"sort": "name", "order": "desc", "limit": 1, "offset": 1},
            headers=actors.employee,
        ).json()
        assert [b["name"] for b in page["items"]] == ["Annex"]
        assert page["total"] == 2


class TestBuildingGet:
    def test_the_404_200_pair_on_the_same_retired_id(
        self, facilities_client: TestClient, actors: Actors, world: World
    ) -> None:
        hidden = facilities_client.get(f"{P}/buildings/{world.old.id}", headers=actors.employee)
        assert (hidden.status_code, hidden.json()["error"]) == (404, "not_found")
        shown = facilities_client.get(f"{P}/buildings/{world.old.id}", headers=actors.admin)
        assert shown.status_code == 200
        assert shown.json()["is_active"] is False

    def test_an_active_building_is_visible_to_everyone(
        self, facilities_client: TestClient, actors: Actors, world: World
    ) -> None:
        body = facilities_client.get(f"{P}/buildings/{world.hq.id}", headers=actors.engineer).json()
        assert body == {
            "id": str(world.hq.id),
            "code": "HQ",
            "name": "Headquarters",
            "address": "1 Main St",
            "is_active": True,
        }

    def test_an_unknown_id_is_not_found(
        self, facilities_client: TestClient, actors: Actors
    ) -> None:
        resp = facilities_client.get(f"{P}/buildings/{uuid.uuid4()}", headers=actors.admin)
        assert resp.status_code == 404


class TestBuildingCreate:
    def test_creates_and_points_at_the_new_row(
        self, facilities_client: TestClient, actors: Actors, verify_session: Session
    ) -> None:
        resp = facilities_client.post(
            f"{P}/buildings", json={"code": "ANNEX", "name": "Annex"}, headers=actors.admin
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert resp.headers["Location"] == f"{P}/buildings/{body['id']}"
        assert body["address"] is None and body["is_active"] is True
        row = stored(verify_session, Building, body["id"])
        assert (row.code, row.name) == ("ANNEX", "Annex")

    def test_a_duplicate_code_is_a_conflict(
        self, facilities_client: TestClient, actors: Actors
    ) -> None:
        resp = facilities_client.post(
            f"{P}/buildings", json={"code": "HQ", "name": "Again"}, headers=actors.admin
        )
        assert (resp.status_code, resp.json()["error"]) == (409, "conflict")

    def test_the_body_is_strict(self, facilities_client: TestClient, actors: Actors) -> None:
        resp = facilities_client.post(
            f"{P}/buildings",
            json={"code": "X", "name": "X", "is_active": False},
            headers=actors.admin,
        )
        assert (resp.status_code, resp.json()["error"]) == (400, "validation_error")


class TestBuildingUpdate:
    def test_omitted_fields_are_unchanged_and_null_clears(
        self, facilities_client: TestClient, actors: Actors, world: World, verify_session: Session
    ) -> None:
        url = f"{P}/buildings/{world.hq.id}"
        renamed = facilities_client.put(url, json={"name": "Head Office"}, headers=actors.admin)
        assert renamed.status_code == 200, renamed.text
        assert (renamed.json()["name"], renamed.json()["address"]) == ("Head Office", "1 Main St")
        cleared = facilities_client.put(url, json={"address": None}, headers=actors.admin)
        assert cleared.json()["address"] is None
        row = stored(verify_session, Building, world.hq.id)
        assert (row.name, row.address, row.code) == ("Head Office", None, "HQ")

    def test_a_required_field_cannot_be_nulled(
        self, facilities_client: TestClient, actors: Actors, world: World
    ) -> None:
        resp = facilities_client.put(
            f"{P}/buildings/{world.hq.id}", json={"name": None}, headers=actors.admin
        )
        assert (resp.status_code, resp.json()["error"]) == (400, "validation_error")

    def test_the_code_is_immutable(
        self, facilities_client: TestClient, actors: Actors, world: World
    ) -> None:
        resp = facilities_client.put(
            f"{P}/buildings/{world.hq.id}", json={"code": "HQ2"}, headers=actors.admin
        )
        assert resp.status_code == 400

    def test_deactivating_hides_it_from_non_admins(
        self, facilities_client: TestClient, actors: Actors, world: World
    ) -> None:
        url = f"{P}/buildings/{world.hq.id}"
        assert facilities_client.get(url, headers=actors.employee).status_code == 200
        resp = facilities_client.put(url, json={"is_active": False}, headers=actors.admin)
        assert resp.json()["is_active"] is False
        assert facilities_client.get(url, headers=actors.employee).status_code == 404
        assert facilities_client.get(url, headers=actors.admin).status_code == 200

    def test_an_unknown_building_is_not_found(
        self, facilities_client: TestClient, actors: Actors
    ) -> None:
        resp = facilities_client.put(
            f"{P}/buildings/{uuid.uuid4()}", json={"name": "X"}, headers=actors.admin
        )
        assert resp.status_code == 404


class TestBuildingDelete:
    def test_an_empty_building_is_deleted(
        self, facilities_client: TestClient, actors: Actors, api: Api, verify_session: Session
    ) -> None:
        created = api.building(actors.admin)
        resp = facilities_client.delete(f"{P}/buildings/{created['id']}", headers=actors.admin)
        assert resp.status_code == 204
        assert stored(verify_session, Building, created["id"]) is None

    def test_a_building_with_floors_is_refused_and_its_floors_survive(
        self, facilities_client: TestClient, actors: Actors, world: World, verify_session: Session
    ) -> None:
        """T72: the FK would cascade, so the service must refuse before the database sees it."""
        resp = facilities_client.delete(f"{P}/buildings/{world.hq.id}", headers=actors.admin)
        assert (resp.status_code, resp.json()["error"]) == (409, "conflict")
        assert resp.json()["message"] == (
            "Building has 2 floors and 0 incidents; deactivate it instead."
        )
        assert stored(verify_session, Building, world.hq.id) is not None
        assert count(verify_session, Floor, building_id=world.hq.id) == 2
        assert count(verify_session, Seat, floor_id=world.ground.id) == 2

    def test_a_building_with_incidents_is_refused(
        self,
        facilities_client: TestClient,
        actors: Actors,
        api: Api,
        make_incident: Any,
        verify_session: Session,
    ) -> None:
        created = api.building(actors.admin)
        make_incident(building_id=uuid.UUID(created["id"]))
        resp = facilities_client.delete(f"{P}/buildings/{created['id']}", headers=actors.admin)
        assert resp.status_code == 409
        assert resp.json()["message"] == (
            "Building has 0 floors and 1 incident; deactivate it instead."
        )
        assert stored(verify_session, Building, created["id"]) is not None

    def test_the_database_restriction_is_a_conflict_too(
        self,
        facilities_client: TestClient,
        actors: Actors,
        api: Api,
        make_incident: Any,
        verify_session: Session,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Miss the pre-check on purpose: the RESTRICT foreign key must still surface as 409."""
        from facilities_service import repository

        created = api.building(actors.admin)
        # Read the id now: the refused request rolls the session back, which
        # expires the object, and a later attribute read would open a new
        # transaction on the test session behind the verify session's back.
        incident_id = make_incident(building_id=uuid.UUID(created["id"])).id
        monkeypatch.setattr(repository, "count_incidents_in_building", lambda s, b: 0)
        resp = facilities_client.delete(f"{P}/buildings/{created['id']}", headers=actors.admin)
        assert (resp.status_code, resp.json()["error"]) == (409, "conflict")
        assert stored(verify_session, Building, created["id"]) is not None
        assert stored(verify_session, Incident, incident_id) is not None

    def test_an_unknown_building_is_not_found(
        self, facilities_client: TestClient, actors: Actors
    ) -> None:
        resp = facilities_client.delete(f"{P}/buildings/{uuid.uuid4()}", headers=actors.admin)
        assert resp.status_code == 404


# --------------------------------------------------------------------------- floors


class TestFloorList:
    def test_lists_a_buildings_floors_lowest_first(
        self, facilities_client: TestClient, actors: Actors, api: Api, world: World
    ) -> None:
        api.floor(actors.admin, level=-1, name="Basement")
        page = facilities_client.get(
            f"{P}/buildings/{world.hq.id}/floors", headers=actors.employee
        ).json()
        assert [(f["level"], f["name"]) for f in page["items"]] == [
            (-1, "Basement"),
            (1, "Ground"),
            (2, None),
        ]
        assert page["total"] == 3
        assert all(f["building_id"] == str(world.hq.id) for f in page["items"])

    def test_sorts_by_name_on_request(
        self, facilities_client: TestClient, actors: Actors, world: World
    ) -> None:
        page = facilities_client.get(
            f"{P}/buildings/{world.hq.id}/floors",
            params={"sort": "name", "order": "desc"},
            headers=actors.employee,
        ).json()
        assert [f["level"] for f in page["items"]] == [2, 1]

    def test_a_retired_buildings_floors_are_for_admins_only(
        self, facilities_client: TestClient, actors: Actors, world: World
    ) -> None:
        url = f"{P}/buildings/{world.old.id}/floors"
        assert facilities_client.get(url, headers=actors.employee).status_code == 404
        page = facilities_client.get(url, headers=actors.admin).json()
        assert [f["level"] for f in page["items"]] == [1]

    def test_an_unknown_building_is_not_found(
        self, facilities_client: TestClient, actors: Actors
    ) -> None:
        resp = facilities_client.get(f"{P}/buildings/{uuid.uuid4()}/floors", headers=actors.admin)
        assert resp.status_code == 404


class TestFloorGet:
    def test_a_floor_is_as_visible_as_its_building(
        self, facilities_client: TestClient, actors: Actors, world: World
    ) -> None:
        url = f"{P}/floors/{world.old_floor.id}"
        hidden = facilities_client.get(url, headers=actors.employee)
        assert (hidden.status_code, hidden.json()["error"]) == (404, "not_found")
        assert facilities_client.get(url, headers=actors.admin).status_code == 200

    def test_returns_the_floor(
        self, facilities_client: TestClient, actors: Actors, world: World
    ) -> None:
        body = facilities_client.get(f"{P}/floors/{world.ground.id}", headers=actors.employee)
        assert body.json() == {
            "id": str(world.ground.id),
            "building_id": str(world.hq.id),
            "level": 1,
            "name": "Ground",
        }


class TestFloorCreate:
    def test_creates_and_points_at_the_new_row(
        self, facilities_client: TestClient, actors: Actors, world: World, verify_session: Session
    ) -> None:
        resp = facilities_client.post(
            f"{P}/floors",
            json={"building_id": str(world.hq.id), "level": 3, "name": "Third"},
            headers=actors.admin,
        )
        assert resp.status_code == 201, resp.text
        assert resp.headers["Location"] == f"{P}/floors/{resp.json()['id']}"
        row = stored(verify_session, Floor, resp.json()["id"])
        assert (row.building_id, row.level, row.name) == (world.hq.id, 3, "Third")

    def test_an_unknown_building_is_a_validation_error_on_the_field(
        self, facilities_client: TestClient, actors: Actors
    ) -> None:
        resp = facilities_client.post(
            f"{P}/floors", json={"building_id": str(uuid.uuid4()), "level": 3}, headers=actors.admin
        )
        assert (resp.status_code, resp.json()["error"]) == (400, "validation_error")
        assert [d["field"] for d in resp.json()["details"]] == ["building_id"]

    def test_a_duplicate_level_is_a_conflict(
        self, facilities_client: TestClient, actors: Actors, world: World
    ) -> None:
        resp = facilities_client.post(
            f"{P}/floors", json={"building_id": str(world.hq.id), "level": 1}, headers=actors.admin
        )
        assert (resp.status_code, resp.json()["error"]) == (409, "conflict")

    def test_non_admins_are_refused(
        self, facilities_client: TestClient, actors: Actors, world: World
    ) -> None:
        resp = facilities_client.post(
            f"{P}/floors",
            json={"building_id": str(world.hq.id), "level": 9},
            headers=actors.engineer,
        )
        assert resp.status_code == 403


class TestFloorUpdate:
    def test_changes_level_and_clears_name(
        self, facilities_client: TestClient, actors: Actors, world: World, verify_session: Session
    ) -> None:
        url = f"{P}/floors/{world.ground.id}"
        resp = facilities_client.put(url, json={"level": 0, "name": None}, headers=actors.admin)
        assert resp.status_code == 200, resp.text
        assert (resp.json()["level"], resp.json()["name"]) == (0, None)
        row = stored(verify_session, Floor, world.ground.id)
        assert (row.level, row.name) == (0, None)

    def test_moving_onto_an_existing_level_is_a_conflict(
        self, facilities_client: TestClient, actors: Actors, world: World
    ) -> None:
        resp = facilities_client.put(
            f"{P}/floors/{world.ground.id}", json={"level": 2}, headers=actors.admin
        )
        assert (resp.status_code, resp.json()["error"]) == (409, "conflict")

    @pytest.mark.parametrize("body", [{"level": None}, {"building_id": NIL}])
    def test_rejects_a_null_level_and_re_parenting(
        self, facilities_client: TestClient, actors: Actors, world: World, body: dict[str, Any]
    ) -> None:
        resp = facilities_client.put(
            f"{P}/floors/{world.ground.id}", json=body, headers=actors.admin
        )
        assert (resp.status_code, resp.json()["error"]) == (400, "validation_error")

    def test_an_unknown_floor_is_not_found(
        self, facilities_client: TestClient, actors: Actors
    ) -> None:
        resp = facilities_client.put(
            f"{P}/floors/{uuid.uuid4()}", json={"level": 5}, headers=actors.admin
        )
        assert resp.status_code == 404


class TestFloorDelete:
    def test_an_empty_floor_is_deleted(
        self, facilities_client: TestClient, actors: Actors, world: World, verify_session: Session
    ) -> None:
        resp = facilities_client.delete(f"{P}/floors/{world.second.id}", headers=actors.admin)
        assert resp.status_code == 204
        assert stored(verify_session, Floor, world.second.id) is None

    def test_a_floor_with_seats_is_refused_and_its_seats_survive(
        self, facilities_client: TestClient, actors: Actors, world: World, verify_session: Session
    ) -> None:
        resp = facilities_client.delete(f"{P}/floors/{world.ground.id}", headers=actors.admin)
        assert (resp.status_code, resp.json()["error"]) == (409, "conflict")
        assert resp.json()["message"] == (
            "Floor has 2 seats and 0 incidents; it cannot be deleted while either remains."
        )
        assert stored(verify_session, Floor, world.ground.id) is not None
        assert count(verify_session, Seat, floor_id=world.ground.id) == 2

    def test_a_floor_named_by_an_incident_is_refused_and_the_incident_keeps_it(
        self,
        facilities_client: TestClient,
        actors: Actors,
        world: World,
        make_incident: Any,
        verify_session: Session,
    ) -> None:
        """The FK is SET NULL, so only this check stands between the delete and a lost location."""
        floor_id = world.second.id
        incident_id = make_incident(floor_id=floor_id).id
        resp = facilities_client.delete(f"{P}/floors/{floor_id}", headers=actors.admin)
        assert resp.status_code == 409
        assert resp.json()["message"].startswith("Floor has 0 seats and 1 incident;")
        assert stored(verify_session, Incident, incident_id).floor_id == floor_id

    def test_a_non_admin_is_refused_before_the_lookup(
        self, facilities_client: TestClient, actors: Actors
    ) -> None:
        resp = facilities_client.delete(f"{P}/floors/{uuid.uuid4()}", headers=actors.employee)
        assert resp.status_code == 403

    def test_an_unknown_floor_is_not_found(
        self, facilities_client: TestClient, actors: Actors
    ) -> None:
        resp = facilities_client.delete(f"{P}/floors/{uuid.uuid4()}", headers=actors.admin)
        assert resp.status_code == 404


# --------------------------------------------------------------------------- seats


class TestSeatList:
    def test_non_admins_see_active_seats_in_code_order(
        self, facilities_client: TestClient, actors: Actors, api: Api, world: World
    ) -> None:
        api.seat(actors.admin, code="1-00")
        page = facilities_client.get(f"{P}/floors/{world.ground.id}/seats", headers=actors.employee)
        assert [s["code"] for s in page.json()["items"]] == ["1-00", "1-01"]
        assert page.json()["total"] == 2

    def test_include_inactive_is_honoured_for_admins_only(
        self, facilities_client: TestClient, actors: Actors, world: World
    ) -> None:
        url = f"{P}/floors/{world.ground.id}/seats"
        params = {"include_inactive": "true"}
        mine = facilities_client.get(url, params=params, headers=actors.employee).json()
        theirs = facilities_client.get(url, params=params, headers=actors.admin).json()
        assert ([s["code"] for s in mine["items"]], mine["total"]) == (["1-01"], 1)
        assert ([s["code"] for s in theirs["items"]], theirs["total"]) == (["1-01", "1-02"], 2)

    def test_search_matches_code_or_label_and_sort_by_label(
        self, facilities_client: TestClient, actors: Actors, api: Api, world: World
    ) -> None:
        api.seat(actors.admin, code="1-03", label="Aisle")
        url = f"{P}/floors/{world.ground.id}/seats"
        found = facilities_client.get(url, params={"search": "wind"}, headers=actors.employee)
        assert [s["code"] for s in found.json()["items"]] == ["1-01"]
        by_label = facilities_client.get(
            url, params={"sort": "label", "order": "desc"}, headers=actors.employee
        )
        assert [s["label"] for s in by_label.json()["items"]] == ["Window", "Aisle"]

    def test_a_floor_in_a_retired_building_is_for_admins_only(
        self, facilities_client: TestClient, actors: Actors, world: World
    ) -> None:
        url = f"{P}/floors/{world.old_floor.id}/seats"
        assert facilities_client.get(url, headers=actors.employee).status_code == 404
        page = facilities_client.get(url, headers=actors.admin).json()
        assert [s["code"] for s in page["items"]] == ["1-01"]

    def test_an_unknown_floor_is_not_found(
        self, facilities_client: TestClient, actors: Actors
    ) -> None:
        resp = facilities_client.get(f"{P}/floors/{uuid.uuid4()}/seats", headers=actors.admin)
        assert resp.status_code == 404


class TestSeatGet:
    @pytest.mark.parametrize("which", ["retired_seat", "old_seat"])
    def test_the_404_200_pair_on_a_seat_nobody_should_be_offered(
        self, facilities_client: TestClient, actors: Actors, world: World, which: str
    ) -> None:
        """A retired seat, and an active seat in a retired building, look alike to an employee."""
        url = f"{P}/seats/{getattr(world, which).id}"
        hidden = facilities_client.get(url, headers=actors.employee)
        assert (hidden.status_code, hidden.json()["error"]) == (404, "not_found")
        assert facilities_client.get(url, headers=actors.admin).status_code == 200

    def test_returns_the_seat(
        self, facilities_client: TestClient, actors: Actors, world: World
    ) -> None:
        body = facilities_client.get(f"{P}/seats/{world.seat.id}", headers=actors.engineer)
        assert body.json() == {
            "id": str(world.seat.id),
            "floor_id": str(world.ground.id),
            "code": "1-01",
            "label": "Window",
            "is_active": True,
        }


class TestSeatCreate:
    def test_creates_and_points_at_the_new_row(
        self, facilities_client: TestClient, actors: Actors, world: World, verify_session: Session
    ) -> None:
        resp = facilities_client.post(
            f"{P}/seats",
            json={"floor_id": str(world.ground.id), "code": "1-03", "label": "Corner"},
            headers=actors.admin,
        )
        assert resp.status_code == 201, resp.text
        assert resp.headers["Location"] == f"{P}/seats/{resp.json()['id']}"
        row = stored(verify_session, Seat, resp.json()["id"])
        assert (row.floor_id, row.code, row.label, row.is_active) == (
            world.ground.id,
            "1-03",
            "Corner",
            True,
        )

    def test_the_same_code_on_another_floor_is_fine(
        self, facilities_client: TestClient, actors: Actors, api: Api, world: World
    ) -> None:
        created = api.seat(actors.admin, floor_id=str(world.second.id), code="1-01")
        assert created["floor_id"] == str(world.second.id)

    def test_an_unknown_floor_is_a_validation_error_on_the_field(
        self, facilities_client: TestClient, actors: Actors
    ) -> None:
        resp = facilities_client.post(
            f"{P}/seats", json={"floor_id": str(uuid.uuid4()), "code": "X"}, headers=actors.admin
        )
        assert (resp.status_code, resp.json()["error"]) == (400, "validation_error")
        assert [d["field"] for d in resp.json()["details"]] == ["floor_id"]

    def test_a_duplicate_code_is_a_conflict(
        self, facilities_client: TestClient, actors: Actors, world: World
    ) -> None:
        resp = facilities_client.post(
            f"{P}/seats",
            json={"floor_id": str(world.ground.id), "code": "1-01"},
            headers=actors.admin,
        )
        assert (resp.status_code, resp.json()["error"]) == (409, "conflict")

    def test_non_admins_are_refused(
        self, facilities_client: TestClient, actors: Actors, world: World
    ) -> None:
        resp = facilities_client.post(
            f"{P}/seats",
            json={"floor_id": str(world.ground.id), "code": "9"},
            headers=actors.employee,
        )
        assert resp.status_code == 403


class TestSeatUpdate:
    def test_changes_code_and_clears_label(
        self, facilities_client: TestClient, actors: Actors, world: World, verify_session: Session
    ) -> None:
        url = f"{P}/seats/{world.seat.id}"
        resp = facilities_client.put(
            url, json={"code": "1-01A", "label": None}, headers=actors.admin
        )
        assert resp.status_code == 200, resp.text
        row = stored(verify_session, Seat, world.seat.id)
        assert (row.code, row.label) == ("1-01A", None)

    def test_renaming_onto_an_existing_code_is_a_conflict(
        self, facilities_client: TestClient, actors: Actors, world: World
    ) -> None:
        resp = facilities_client.put(
            f"{P}/seats/{world.seat.id}", json={"code": "1-02"}, headers=actors.admin
        )
        assert (resp.status_code, resp.json()["error"]) == (409, "conflict")

    def test_a_required_field_cannot_be_nulled(
        self, facilities_client: TestClient, actors: Actors, world: World
    ) -> None:
        resp = facilities_client.put(
            f"{P}/seats/{world.seat.id}", json={"code": None}, headers=actors.admin
        )
        assert resp.status_code == 400

    def test_deactivating_hides_it_from_non_admins(
        self, facilities_client: TestClient, actors: Actors, world: World
    ) -> None:
        url = f"{P}/seats/{world.seat.id}"
        resp = facilities_client.put(url, json={"is_active": False}, headers=actors.admin)
        assert resp.json()["is_active"] is False
        assert facilities_client.get(url, headers=actors.employee).status_code == 404
        listed = facilities_client.get(
            f"{P}/floors/{world.ground.id}/seats", headers=actors.employee
        )
        assert listed.json()["items"] == []

    def test_an_unknown_seat_is_not_found(
        self, facilities_client: TestClient, actors: Actors
    ) -> None:
        resp = facilities_client.put(
            f"{P}/seats/{uuid.uuid4()}", json={"code": "Z"}, headers=actors.admin
        )
        assert resp.status_code == 404


class TestSeatDelete:
    def test_an_unused_seat_is_deleted(
        self, facilities_client: TestClient, actors: Actors, world: World, verify_session: Session
    ) -> None:
        resp = facilities_client.delete(f"{P}/seats/{world.retired_seat.id}", headers=actors.admin)
        assert resp.status_code == 204
        assert stored(verify_session, Seat, world.retired_seat.id) is None

    def test_a_seat_named_by_an_incident_is_refused_and_the_incident_keeps_it(
        self,
        facilities_client: TestClient,
        actors: Actors,
        world: World,
        make_incident: Any,
        verify_session: Session,
    ) -> None:
        """The FK is SET NULL, so only this check stands between the delete and a lost location."""
        seat_id = world.seat.id
        incident_id = make_incident(floor_id=world.ground.id, seat_id=seat_id).id
        resp = facilities_client.delete(f"{P}/seats/{seat_id}", headers=actors.admin)
        assert (resp.status_code, resp.json()["error"]) == (409, "conflict")
        assert resp.json()["message"] == "Seat is referenced by 1 incident; deactivate it instead."
        assert stored(verify_session, Seat, seat_id) is not None
        assert stored(verify_session, Incident, incident_id).seat_id == seat_id

    def test_a_non_admin_is_refused_before_the_lookup(
        self, facilities_client: TestClient, actors: Actors
    ) -> None:
        resp = facilities_client.delete(f"{P}/seats/{uuid.uuid4()}", headers=actors.engineer)
        assert resp.status_code == 403

    def test_an_unknown_seat_is_not_found(
        self, facilities_client: TestClient, actors: Actors
    ) -> None:
        resp = facilities_client.delete(f"{P}/seats/{uuid.uuid4()}", headers=actors.admin)
        assert resp.status_code == 404


# --------------------------------------------------------------------------- categories


class TestCategoryList:
    def test_non_admins_see_active_categories_flat_by_name(
        self, facilities_client: TestClient, actors: Actors, world: World
    ) -> None:
        page = facilities_client.get(f"{P}/categories", headers=actors.employee).json()
        assert [(c["name"], c["parent_id"]) for c in page["items"]] == [
            ("Facilities", None),
            ("HVAC", str(world.facilities.id)),
        ]
        assert page["total"] == 2

    def test_include_inactive_is_honoured_for_admins_only(
        self, facilities_client: TestClient, actors: Actors
    ) -> None:
        params = {"include_inactive": "true"}
        mine = facilities_client.get(f"{P}/categories", params=params, headers=actors.employee)
        theirs = facilities_client.get(f"{P}/categories", params=params, headers=actors.admin)
        assert mine.json()["total"] == 2
        assert [c["name"] for c in theirs.json()["items"]] == ["Facilities", "HVAC", "Retired"]

    def test_roots_only_and_children_of_a_parent(
        self, facilities_client: TestClient, actors: Actors, world: World
    ) -> None:
        roots = facilities_client.get(
            f"{P}/categories", params={"roots_only": "true"}, headers=actors.employee
        )
        assert [c["name"] for c in roots.json()["items"]] == ["Facilities"]
        children = facilities_client.get(
            f"{P}/categories",
            params={"parent_id": str(world.facilities.id)},
            headers=actors.employee,
        )
        assert [c["name"] for c in children.json()["items"]] == ["HVAC"]

    def test_an_unknown_parent_filter_is_an_empty_page(
        self, facilities_client: TestClient, actors: Actors
    ) -> None:
        resp = facilities_client.get(
            f"{P}/categories", params={"parent_id": str(uuid.uuid4())}, headers=actors.employee
        )
        assert resp.status_code == 200
        assert (resp.json()["items"], resp.json()["total"]) == ([], 0)

    def test_roots_only_and_parent_id_cannot_combine(
        self, facilities_client: TestClient, actors: Actors, world: World
    ) -> None:
        resp = facilities_client.get(
            f"{P}/categories",
            params={"roots_only": "true", "parent_id": str(world.facilities.id)},
            headers=actors.employee,
        )
        assert (resp.status_code, resp.json()["error"]) == (400, "validation_error")

    def test_search_matches_the_name(self, facilities_client: TestClient, actors: Actors) -> None:
        resp = facilities_client.get(
            f"{P}/categories", params={"search": "hv"}, headers=actors.employee
        )
        assert [c["name"] for c in resp.json()["items"]] == ["HVAC"]


class TestCategoryGet:
    def test_the_404_200_pair_on_the_same_retired_id(
        self, facilities_client: TestClient, actors: Actors, world: World
    ) -> None:
        url = f"{P}/categories/{world.retired_category.id}"
        hidden = facilities_client.get(url, headers=actors.employee)
        assert (hidden.status_code, hidden.json()["error"]) == (404, "not_found")
        assert facilities_client.get(url, headers=actors.admin).status_code == 200

    def test_returns_the_category(
        self, facilities_client: TestClient, actors: Actors, world: World
    ) -> None:
        body = facilities_client.get(f"{P}/categories/{world.hvac.id}", headers=actors.engineer)
        assert body.json() == {
            "id": str(world.hvac.id),
            "name": "HVAC",
            "parent_id": str(world.facilities.id),
            "description": None,
            "is_active": True,
        }


class TestCategoryCreate:
    def test_creates_a_root_and_points_at_it(
        self, facilities_client: TestClient, actors: Actors, verify_session: Session
    ) -> None:
        resp = facilities_client.post(
            f"{P}/categories",
            json={"name": "Workplace", "description": "Desks and chairs"},
            headers=actors.admin,
        )
        assert resp.status_code == 201, resp.text
        assert resp.headers["Location"] == f"{P}/categories/{resp.json()['id']}"
        row = stored(verify_session, Category, resp.json()["id"])
        assert (row.name, row.parent_id, row.description) == ("Workplace", None, "Desks and chairs")

    def test_creates_a_child_of_a_root(
        self, facilities_client: TestClient, actors: Actors, api: Api, world: World
    ) -> None:
        created = api.category(actors.admin, name="Lighting", parent_id=str(world.facilities.id))
        assert created["parent_id"] == str(world.facilities.id)

    def test_a_child_may_share_a_name_with_a_root(
        self, facilities_client: TestClient, actors: Actors, api: Api, world: World
    ) -> None:
        """Sibling names must differ; the same name under a different parent is fine."""
        assert api.category(actors.admin, name="HVAC")["parent_id"] is None

    @pytest.mark.parametrize("parent", ["hvac", "missing"])
    def test_the_parent_must_be_an_existing_root(
        self, facilities_client: TestClient, actors: Actors, world: World, parent: str
    ) -> None:
        parent_id = str(world.hvac.id) if parent == "hvac" else str(uuid.uuid4())
        resp = facilities_client.post(
            f"{P}/categories", json={"name": "Deep", "parent_id": parent_id}, headers=actors.admin
        )
        assert (resp.status_code, resp.json()["error"]) == (400, "validation_error")
        assert [d["field"] for d in resp.json()["details"]] == ["parent_id"]

    def test_a_duplicate_root_name_is_a_conflict(
        self, facilities_client: TestClient, actors: Actors
    ) -> None:
        """Roots have a NULL parent, which the unique constraint cannot see; the service must."""
        resp = facilities_client.post(
            f"{P}/categories", json={"name": "Facilities"}, headers=actors.admin
        )
        assert (resp.status_code, resp.json()["error"]) == (409, "conflict")

    def test_a_duplicate_sibling_name_is_a_conflict(
        self, facilities_client: TestClient, actors: Actors, world: World
    ) -> None:
        resp = facilities_client.post(
            f"{P}/categories",
            json={"name": "HVAC", "parent_id": str(world.facilities.id)},
            headers=actors.admin,
        )
        assert (resp.status_code, resp.json()["error"]) == (409, "conflict")

    def test_non_admins_are_refused(self, facilities_client: TestClient, actors: Actors) -> None:
        resp = facilities_client.post(
            f"{P}/categories", json={"name": "X"}, headers=actors.employee
        )
        assert resp.status_code == 403


class TestCategoryUpdate:
    def test_renames_and_clears_the_description(
        self, facilities_client: TestClient, actors: Actors, api: Api, verify_session: Session
    ) -> None:
        created = api.category(actors.admin, description="temp")
        resp = facilities_client.put(
            f"{P}/categories/{created['id']}",
            json={"name": "Workspace", "description": None},
            headers=actors.admin,
        )
        assert resp.status_code == 200, resp.text
        row = stored(verify_session, Category, created["id"])
        assert (row.name, row.description) == ("Workspace", None)

    def test_renaming_a_root_onto_another_root_is_a_conflict(
        self, facilities_client: TestClient, actors: Actors, api: Api
    ) -> None:
        created = api.category(actors.admin)
        resp = facilities_client.put(
            f"{P}/categories/{created['id']}", json={"name": "Facilities"}, headers=actors.admin
        )
        assert (resp.status_code, resp.json()["error"]) == (409, "conflict")

    def test_renaming_a_child_onto_a_sibling_is_a_conflict(
        self, facilities_client: TestClient, actors: Actors, api: Api, world: World
    ) -> None:
        sibling = api.category(actors.admin, name="Lighting", parent_id=str(world.facilities.id))
        resp = facilities_client.put(
            f"{P}/categories/{sibling['id']}", json={"name": "HVAC"}, headers=actors.admin
        )
        assert (resp.status_code, resp.json()["error"]) == (409, "conflict")

    def test_renaming_to_its_own_name_is_fine(
        self, facilities_client: TestClient, actors: Actors, world: World
    ) -> None:
        resp = facilities_client.put(
            f"{P}/categories/{world.facilities.id}",
            json={"name": "Facilities"},
            headers=actors.admin,
        )
        assert resp.status_code == 200

    @pytest.mark.parametrize("body", [{"name": None}, {"parent_id": None}])
    def test_rejects_a_null_name_and_re_parenting(
        self, facilities_client: TestClient, actors: Actors, world: World, body: dict[str, Any]
    ) -> None:
        resp = facilities_client.put(
            f"{P}/categories/{world.hvac.id}", json=body, headers=actors.admin
        )
        assert (resp.status_code, resp.json()["error"]) == (400, "validation_error")

    def test_deactivating_a_root_hides_it_but_not_its_children(
        self, facilities_client: TestClient, actors: Actors, world: World
    ) -> None:
        """Documented, not cascaded: the client builds the tree from active roots."""
        resp = facilities_client.put(
            f"{P}/categories/{world.facilities.id}", json={"is_active": False}, headers=actors.admin
        )
        assert resp.json()["is_active"] is False
        page = facilities_client.get(f"{P}/categories", headers=actors.employee).json()
        assert [c["name"] for c in page["items"]] == ["HVAC"]

    def test_an_unknown_category_is_not_found(
        self, facilities_client: TestClient, actors: Actors
    ) -> None:
        resp = facilities_client.put(
            f"{P}/categories/{uuid.uuid4()}", json={"name": "X"}, headers=actors.admin
        )
        assert resp.status_code == 404


class TestCategoryDelete:
    def test_a_leaf_is_deleted(
        self, facilities_client: TestClient, actors: Actors, world: World, verify_session: Session
    ) -> None:
        resp = facilities_client.delete(f"{P}/categories/{world.hvac.id}", headers=actors.admin)
        assert resp.status_code == 204
        assert stored(verify_session, Category, world.hvac.id) is None

    def test_a_parent_is_refused_and_its_children_keep_their_parent(
        self, facilities_client: TestClient, actors: Actors, world: World, verify_session: Session
    ) -> None:
        parent_id, child_id = world.facilities.id, world.hvac.id
        resp = facilities_client.delete(f"{P}/categories/{parent_id}", headers=actors.admin)
        assert (resp.status_code, resp.json()["error"]) == (409, "conflict")
        assert resp.json()["message"] == (
            "Category has 1 sub-category and 0 incidents; deactivate it instead."
        )
        assert stored(verify_session, Category, parent_id) is not None
        assert stored(verify_session, Category, child_id).parent_id == parent_id

    def test_a_category_carried_by_an_incident_is_refused(
        self,
        facilities_client: TestClient,
        actors: Actors,
        world: World,
        make_incident: Any,
        verify_session: Session,
    ) -> None:
        category_id = world.hvac.id
        incident_id = make_incident(category_id=category_id).id
        resp = facilities_client.delete(f"{P}/categories/{category_id}", headers=actors.admin)
        assert resp.status_code == 409
        assert resp.json()["message"] == (
            "Category has 0 sub-categories and 1 incident; deactivate it instead."
        )
        assert stored(verify_session, Incident, incident_id).category_id == category_id

    @pytest.mark.parametrize("missed", ["count_children", "count_incidents_in_category"])
    def test_the_database_restriction_is_a_conflict_too(
        self,
        facilities_client: TestClient,
        actors: Actors,
        world: World,
        make_incident: Any,
        verify_session: Session,
        monkeypatch: pytest.MonkeyPatch,
        missed: str,
    ) -> None:
        """Miss a pre-check on purpose: both RESTRICT foreign keys must still surface as 409.

        The children case is the one passive_deletes exists for; without it
        the ORM would null the child's parent first and the delete would go
        through, silently promoting the child to a root.
        """
        from facilities_service import repository

        parent_id, child_id = world.facilities.id, world.hvac.id
        incident_id = make_incident(category_id=parent_id).id
        monkeypatch.setattr(repository, missed, lambda s, c: 0)
        if missed == "count_children":
            monkeypatch.setattr(repository, "count_incidents_in_category", lambda s, c: 0)
        else:
            monkeypatch.setattr(repository, "count_children", lambda s, c: 0)
        resp = facilities_client.delete(f"{P}/categories/{parent_id}", headers=actors.admin)
        assert (resp.status_code, resp.json()["error"]) == (409, "conflict")
        assert stored(verify_session, Category, parent_id) is not None
        assert stored(verify_session, Category, child_id).parent_id == parent_id
        assert stored(verify_session, Incident, incident_id).category_id == parent_id

    def test_a_non_admin_is_refused_before_the_lookup(
        self, facilities_client: TestClient, actors: Actors
    ) -> None:
        resp = facilities_client.delete(f"{P}/categories/{uuid.uuid4()}", headers=actors.employee)
        assert resp.status_code == 403

    def test_an_unknown_category_is_not_found(
        self, facilities_client: TestClient, actors: Actors
    ) -> None:
        resp = facilities_client.delete(f"{P}/categories/{uuid.uuid4()}", headers=actors.admin)
        assert resp.status_code == 404


# --------------------------------------------------------------------------- engineers


class TestEngineerList:
    def test_lists_active_engineers_with_their_user_by_name(
        self, facilities_client: TestClient, actors: Actors, world: World
    ) -> None:
        """Not the employee, not the demoted user with a stale profile, not the inactive one."""
        page = facilities_client.get(f"{P}/engineers", headers=actors.admin).json()
        assert page["total"] == 2
        assert page["items"][0] == {
            "user_id": str(world.engineer.id),
            "specialty": "HVAC",
            "max_concurrent_incidents": 5,
            "is_available": True,
            "user": {"id": str(world.engineer.id), "full_name": "Ada", "role": "Engineer"},
            "open_assignments": 0,
        }
        assert page["items"][1]["user"]["full_name"] == "Bob"

    def test_open_assignments_counts_unfinished_incidents_and_sorts_by_load(
        self, facilities_client: TestClient, actors: Actors, world: World, make_incident: Any
    ) -> None:
        """Resolved and Closed are both finished, as in the engineers report."""
        for status in (
            IncidentStatus.IN_PROGRESS,
            IncidentStatus.BLOCKED,
            IncidentStatus.RESOLVED,
            IncidentStatus.CLOSED,
        ):
            make_incident(assignee_id=world.engineer.id, status=status)
        make_incident(assignee_id=world.other_engineer.id, status=IncidentStatus.OPEN)
        make_incident(assignee_id=world.other_engineer.id, status=IncidentStatus.RESOLVED)
        busiest_first = facilities_client.get(
            f"{P}/engineers",
            params={"sort": "open_assignments", "order": "desc"},
            headers=actors.admin,
        ).json()
        assert [
            (e["user"]["full_name"], e["open_assignments"]) for e in busiest_first["items"]
        ] == [
            ("Ada", 2),
            ("Bob", 1),
        ]
        freest_first = facilities_client.get(
            f"{P}/engineers", params={"sort": "open_assignments"}, headers=actors.admin
        ).json()
        assert [e["user"]["full_name"] for e in freest_first["items"]] == ["Bob", "Ada"]

    def test_filters_by_specialty_case_insensitively_and_by_availability(
        self, facilities_client: TestClient, actors: Actors, world: World
    ) -> None:
        hvac = facilities_client.get(
            f"{P}/engineers", params={"specialty": "hvac"}, headers=actors.admin
        ).json()
        assert ([e["user"]["full_name"] for e in hvac["items"]], hvac["total"]) == (["Ada"], 1)
        nobody = facilities_client.get(
            f"{P}/engineers", params={"specialty": "Masonry"}, headers=actors.admin
        ).json()
        assert (nobody["items"], nobody["total"]) == ([], 0)
        facilities_client.put(
            f"{P}/engineers/{world.engineer.id}", json={"is_available": False}, headers=actors.admin
        )
        available = facilities_client.get(
            f"{P}/engineers", params={"is_available": "true"}, headers=actors.admin
        ).json()
        assert [e["user"]["full_name"] for e in available["items"]] == ["Bob"]

    def test_sorts_by_specialty_and_pages(
        self, facilities_client: TestClient, actors: Actors
    ) -> None:
        page = facilities_client.get(
            f"{P}/engineers", params={"sort": "specialty", "limit": 1}, headers=actors.admin
        ).json()
        assert [e["specialty"] for e in page["items"]] == ["Electrical"]
        assert (page["total"], page["limit"]) == (2, 1)

    def test_only_admins_may_look(self, facilities_client: TestClient, actors: Actors) -> None:
        for headers in (actors.employee, actors.engineer):
            resp = facilities_client.get(f"{P}/engineers", headers=headers)
            assert (resp.status_code, resp.json()["error"]) == (403, "forbidden")


class TestEngineerGet:
    def test_returns_the_profile_with_its_load(
        self, facilities_client: TestClient, actors: Actors, world: World, make_incident: Any
    ) -> None:
        make_incident(assignee_id=world.other_engineer.id, status=IncidentStatus.IN_PROGRESS)
        body = facilities_client.get(
            f"{P}/engineers/{world.other_engineer.id}", headers=actors.admin
        ).json()
        assert (body["specialty"], body["open_assignments"]) == ("Electrical", 1)
        assert body["user"]["full_name"] == "Bob"

    @pytest.mark.parametrize("who", ["employee", "demoted", "inactive_engineer", "admin"])
    def test_anyone_who_is_not_an_active_engineer_is_not_found(
        self, facilities_client: TestClient, actors: Actors, world: World, who: str
    ) -> None:
        """Including the demoted user, whose profile row outlived their role."""
        resp = facilities_client.get(
            f"{P}/engineers/{getattr(world, who).id}", headers=actors.admin
        )
        assert (resp.status_code, resp.json()["error"]) == (404, "not_found")

    def test_an_unknown_id_is_not_found(
        self, facilities_client: TestClient, actors: Actors
    ) -> None:
        resp = facilities_client.get(f"{P}/engineers/{uuid.uuid4()}", headers=actors.admin)
        assert resp.status_code == 404

    def test_a_non_admin_is_refused(
        self, facilities_client: TestClient, actors: Actors, world: World
    ) -> None:
        resp = facilities_client.get(f"{P}/engineers/{world.engineer.id}", headers=actors.engineer)
        assert resp.status_code == 403


class TestEngineerUpdate:
    def test_edits_the_scheduling_fields(
        self, facilities_client: TestClient, actors: Actors, world: World, verify_session: Session
    ) -> None:
        resp = facilities_client.put(
            f"{P}/engineers/{world.engineer.id}",
            json={"specialty": "Plumbing", "max_concurrent_incidents": 3, "is_available": False},
            headers=actors.admin,
        )
        assert resp.status_code == 200, resp.text
        assert (resp.json()["specialty"], resp.json()["max_concurrent_incidents"]) == (
            "Plumbing",
            3,
        )
        row = verify_session.execute(
            select(EngineerProfile).where(EngineerProfile.user_id == world.engineer.id)
        ).scalar_one()
        verify_session.refresh(row)
        assert (row.specialty, row.max_concurrent_incidents, row.is_available) == (
            "Plumbing",
            3,
            False,
        )

    @pytest.mark.parametrize(
        "body", [{"max_concurrent_incidents": 0}, {"specialty": None}, {"user_id": NIL}]
    )
    def test_rejects_zero_capacity_nulls_and_unknown_fields(
        self, facilities_client: TestClient, actors: Actors, world: World, body: dict[str, Any]
    ) -> None:
        resp = facilities_client.put(
            f"{P}/engineers/{world.engineer.id}", json=body, headers=actors.admin
        )
        assert (resp.status_code, resp.json()["error"]) == (400, "validation_error")

    def test_a_demoted_user_cannot_be_edited_here(
        self, facilities_client: TestClient, actors: Actors, world: World
    ) -> None:
        resp = facilities_client.put(
            f"{P}/engineers/{world.demoted.id}", json={"is_available": False}, headers=actors.admin
        )
        assert resp.status_code == 404

    def test_a_non_admin_is_refused_before_the_lookup(
        self, facilities_client: TestClient, actors: Actors
    ) -> None:
        resp = facilities_client.put(
            f"{P}/engineers/{uuid.uuid4()}", json={"is_available": False}, headers=actors.engineer
        )
        assert resp.status_code == 403
