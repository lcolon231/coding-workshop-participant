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
    Floor,
    Incident,
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
    PROTECTED_ROUTES = 5

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
