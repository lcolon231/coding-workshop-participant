"""Request and response schemas.

The central assertion here is structural: no request schema may contain a
server-controlled field. That is what closes mass assignment for every current
and future endpoint at once, rather than relying on each handler to remember.
"""

from __future__ import annotations

import uuid

import pytest
from pydantic import BaseModel, ValidationError

from acme_core import schemas
from acme_core.models.enums import IncidentStatus, NoteVisibility, Priority, Role
from acme_core.schemas.common import (
    MAX_PAGE_SIZE,
    SERVER_CONTROLLED_FIELDS,
    Page,
    PageParams,
    StrictModel,
)

pytestmark = pytest.mark.unit

VALID_PASSWORD = "correct-horse-battery"


def request_models() -> list[type[StrictModel]]:
    """Every request schema, found by walking the package's exports."""
    found = []
    for name in schemas.__all__:
        obj = getattr(schemas, name, None)
        if isinstance(obj, type) and issubclass(obj, StrictModel) and obj is not StrictModel:
            found.append(obj)
    return found


def response_models() -> list[type[BaseModel]]:
    found = []
    for name in schemas.__all__:
        obj = getattr(schemas, name, None)
        if (
            isinstance(obj, type)
            and issubclass(obj, BaseModel)
            and not issubclass(obj, StrictModel)
            and obj not in (Page,)
        ):
            found.append(obj)
    return found


class TestMassAssignment:
    """The reason request and response schemas are separate types."""

    # Every deviation, stated with its justification. A schema absent from this
    # table gets no allowance at all, so adding one that accepts a privileged
    # field fails here rather than becoming an escalation later.
    PERMITTED = {
        # Choosing a role is the entire purpose of the admin endpoints; it is
        # why they exist separately from RegisterRequest rather than as an
        # optional field on it.
        "AdminCreateUserRequest": {"role"},
        "AdminUpdateUserRequest": {"role", "is_active"},
        # Whether a building, seat or category is in service is a domain
        # attribute an admin sets, not a security flag like users.is_active.
        # All three endpoints are admin-only.
        "BuildingUpdate": {"is_active"},
        "SeatUpdate": {"is_active"},
        "CategoryUpdate": {"is_active"},
    }

    @pytest.mark.parametrize("model", request_models(), ids=lambda m: m.__name__)
    def test_no_request_schema_assigns_a_server_controlled_field(
        self, model: type[StrictModel]
    ) -> None:
        """Closes mass assignment for every endpoint at once, present and future."""
        if issubclass(model, PageParams):
            pytest.skip("filter schema: these fields narrow a query, never assign")
        allowed = self.PERMITTED.get(model.__name__, set())
        leaked = (set(model.model_fields) & SERVER_CONTROLLED_FIELDS) - allowed
        assert leaked == set(), f"{model.__name__} would accept {sorted(leaked)}"

    @pytest.mark.parametrize("model", request_models(), ids=lambda m: m.__name__)
    def test_filter_schemas_cannot_be_used_to_assign(
        self, model: type[StrictModel]
    ) -> None:
        """A filter schema must never be passed to a constructor.

        IncidentFilters carries `status` so a client can filter by it. That is
        safe only while nothing does Incident(**filters.model_dump()), so the
        two kinds of schema stay structurally distinct types.
        """
        if not issubclass(model, PageParams):
            pytest.skip("not a filter schema")
        assert "limit" in model.model_fields and "offset" in model.model_fields

    @pytest.mark.parametrize("model", request_models(), ids=lambda m: m.__name__)
    def test_every_request_schema_forbids_extra_fields(
        self, model: type[StrictModel]
    ) -> None:
        """Without this an ignored field returns 201 and looks like it worked."""
        assert model.model_config.get("extra") == "forbid"

    def test_incident_create_takes_no_reporter(self) -> None:
        """Otherwise one employee can file an incident as another."""
        assert "reporter_id" not in schemas.IncidentCreate.model_fields

    def test_incident_update_cannot_set_status(self) -> None:
        """Status moves only through the transition endpoint, which applies
        the workflow rules. A generic PUT accepting it bypasses them."""
        assert "status" not in schemas.IncidentUpdate.model_fields


class TestRegistration:
    def test_accepts_a_company_address(self) -> None:
        req = schemas.RegisterRequest(
            email="someone@acme.inc", password=VALID_PASSWORD, full_name="Someone"
        )
        assert req.email == "someone@acme.inc"

    def test_lowercases_and_trims(self) -> None:
        """So the unique index is effectively case-insensitive."""
        req = schemas.RegisterRequest(
            email="  Someone@ACME.INC  ", password=VALID_PASSWORD, full_name="S"
        )
        assert req.email == "someone@acme.inc"

    @pytest.mark.parametrize(
        "email",
        [
            "someone@gmail.com",
            "someone@acme.inc.evil.com",
            "someone@notacme.inc",
            "someone@sub.acme.inc",
        ],
    )
    def test_rejects_other_domains(self, email: str) -> None:
        """The suffix cases matter: a naive endswith check accepts the middle two."""
        with pytest.raises(ValidationError):
            schemas.RegisterRequest(
                email=email, password=VALID_PASSWORD, full_name="S"
            )

    def test_has_no_role_field_at_all(self) -> None:
        """Self-registration always creates an Employee."""
        assert "role" not in schemas.RegisterRequest.model_fields

    def test_supplying_a_role_is_a_validation_error(self) -> None:
        """Not silently ignored: the client is told it was refused."""
        with pytest.raises(ValidationError) as exc:
            schemas.RegisterRequest(
                email="s@acme.inc", password=VALID_PASSWORD,
                full_name="S", role="Facility Admin",
            )
        assert exc.value.errors()[0]["type"] == "extra_forbidden"

    def test_rejects_a_short_password(self) -> None:
        with pytest.raises(ValidationError):
            schemas.RegisterRequest(email="s@acme.inc", password="short", full_name="S")

    def test_rejects_an_empty_name(self) -> None:
        with pytest.raises(ValidationError):
            schemas.RegisterRequest(
                email="s@acme.inc", password=VALID_PASSWORD, full_name="   "
            )


class TestLogin:
    def test_does_not_impose_the_strength_rule(self) -> None:
        """A password policy tightened later must not lock out existing users."""
        assert schemas.LoginRequest(email="s@acme.inc", password="old").password == "old"

    def test_normalises_the_email(self) -> None:
        assert schemas.LoginRequest(email="S@ACME.INC", password="x").email == "s@acme.inc"

    def test_accepts_any_domain(self) -> None:
        """The domain rule gates registration, not sign-in."""
        assert schemas.LoginRequest(email="legacy@other.com", password="x")


class TestIncidentCreation:
    def _payload(self, **kw: object) -> dict[str, object]:
        return {"title": "Broken", "description": "d", "building_id": uuid.uuid4(), **kw}

    def test_building_is_required(self) -> None:
        with pytest.raises(ValidationError):
            schemas.IncidentCreate(title="t", description="d")

    def test_floor_and_seat_are_optional(self) -> None:
        assert schemas.IncidentCreate(**self._payload()).seat_id is None

    def test_a_seat_requires_its_floor(self) -> None:
        """A seat with no floor breaks the UI cascade and means nothing."""
        with pytest.raises(ValidationError, match="floor_id is required"):
            schemas.IncidentCreate(**self._payload(seat_id=uuid.uuid4()))

    def test_a_seat_with_its_floor_is_accepted(self) -> None:
        assert schemas.IncidentCreate(
            **self._payload(floor_id=uuid.uuid4(), seat_id=uuid.uuid4())
        )

    def test_priority_defaults_to_medium(self) -> None:
        assert schemas.IncidentCreate(**self._payload()).priority is Priority.MEDIUM

    def test_an_unknown_priority_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            schemas.IncidentCreate(**self._payload(priority="Apocalyptic"))


class TestFilters:
    def test_defaults_are_sensible(self) -> None:
        filters = schemas.IncidentFilters()
        assert (filters.sort, filters.order, filters.offset) == ("created_at", "desc", 0)

    @pytest.mark.parametrize(
        "sort", ["password_hash", "id; DROP TABLE users", "__class__", "reporter_id"]
    )
    def test_sort_is_an_allowlist(self, sort: str) -> None:
        """ORDER BY cannot be parameterised, so a free-text sort is injectable,
        and getattr(Model, value) allows traversal onto dunder attributes."""
        with pytest.raises(ValidationError):
            schemas.IncidentFilters(sort=sort)

    @pytest.mark.parametrize("sort", ["created_at", "priority", "status", "title"])
    def test_permitted_sorts_are_accepted(self, sort: str) -> None:
        assert schemas.IncidentFilters(sort=sort).sort == sort

    def test_order_is_an_allowlist(self) -> None:
        with pytest.raises(ValidationError):
            schemas.IncidentFilters(order="; DELETE FROM incidents")

    def test_page_size_is_bounded(self) -> None:
        """An unbounded limit is a way to pull the whole table in one request."""
        with pytest.raises(ValidationError):
            PageParams(limit=MAX_PAGE_SIZE + 1)

    def test_negative_offset_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            PageParams(offset=-1)

    def test_status_filter_accepts_only_real_statuses(self) -> None:
        assert schemas.IncidentFilters(status=IncidentStatus.OPEN).status is IncidentStatus.OPEN
        with pytest.raises(ValidationError):
            schemas.IncidentFilters(status="Pending")


class TestTransitionRequest:
    def test_requires_a_target(self) -> None:
        with pytest.raises(ValidationError):
            schemas.TransitionRequest()

    def test_optional_fields_default_to_none(self) -> None:
        """Which is required depends on the edge; the workflow decides, not this."""
        req = schemas.TransitionRequest(target_status=IncidentStatus.RESOLVED)
        assert req.resolution_note is None

    def test_an_unknown_status_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            schemas.TransitionRequest(target_status="Abandoned")


class TestResponses:
    def test_user_out_carries_no_password_hash(self) -> None:
        assert "password_hash" not in schemas.UserOut.model_fields

    def test_user_out_carries_no_lockout_counters(self) -> None:
        """Operational state; exposing it lets a client probe lockout status."""
        fields = set(schemas.UserOut.model_fields)
        assert not fields & {"failed_login_count", "locked_until", "sessions_valid_from"}

    def test_responses_read_from_orm_objects(self) -> None:
        assert schemas.UserOut.model_config.get("from_attributes") is True

    def test_incident_out_exposes_all_four_stamps(self) -> None:
        """The client renders an SLA timeline from these."""
        assert {
            "acknowledged_at", "assigned_at", "resolved_at", "closed_at"
        } <= set(schemas.IncidentOut.model_fields)

    def test_note_out_reports_visibility(self) -> None:
        """So the UI can mark an internal note as such."""
        assert schemas.NoteOut.model_fields["visibility"].annotation is NoteVisibility

    def test_admin_create_may_choose_a_role(self) -> None:
        assert schemas.AdminCreateUserRequest.model_fields["role"].annotation is Role


class TestPage:
    def test_reports_totals_and_window(self) -> None:
        page = Page[int](items=[1, 2], total=10, limit=2, offset=0)
        assert (page.total, page.has_more) == (10, True)

    def test_knows_when_it_is_the_last_page(self) -> None:
        assert Page[int](items=[9, 10], total=10, limit=2, offset=8).has_more is False

    def test_an_empty_page_is_not_more(self) -> None:
        assert Page[int](items=[], total=0, limit=25, offset=0).has_more is False
