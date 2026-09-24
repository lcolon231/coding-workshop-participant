"""Schemas added for the API design (docs/design/api.md §6).

Cross-cutting guarantees -- no request schema assigns a server-controlled field,
every request forbids extras -- live in test_schemas.py and already cover every
schema here, because they walk the package exports.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

import pytest
from pydantic import ValidationError

from acme_core import schemas, workflow
from acme_core.models.enums import (
    EscalationStatus,
    IncidentStatus,
    NoteVisibility,
    Priority,
    Role,
)
from acme_core.models.incident import (
    EscalationRequest,
    Incident,
    IncidentNote,
    IncidentStatusHistory,
)
from acme_core.models.user import User
from acme_core.reporting import DEFAULT_RANGE_DAYS, MAX_RANGE_DAYS, SLA_TARGETS
from acme_core.schemas.common import UpdateModel

pytestmark = pytest.mark.unit

VALID_PASSWORD = "correct-horse-battery"
NOW = dt.datetime(2026, 9, 22, 12, 0, tzinfo=dt.UTC)


def update_models() -> list[type[UpdateModel]]:
    """Every partial-update schema, found by walking the package's exports."""
    return [
        obj
        for name in schemas.__all__
        if isinstance(obj := getattr(schemas, name), type)
        and issubclass(obj, UpdateModel)
        and obj is not UpdateModel
    ]


def error_fields(exc: ValidationError) -> set[str]:
    return {".".join(str(p) for p in err["loc"]) for err in exc.errors()}


def user(role: Role = Role.EMPLOYEE, name: str = "Jane Doe") -> User:
    return User(id=uuid.uuid4(), email="jane@acme.inc", full_name=name, role=role)


def incident(**kw: Any) -> Incident:
    reporter = kw.pop("reporter", user())
    values: dict[str, Any] = {
        "id": uuid.uuid4(),
        "title": "Aircon dripping",
        "description": "Water on desk 3-14",
        "status": IncidentStatus.OPEN,
        "priority": Priority.MEDIUM,
        "reporter_id": reporter.id,
        "reporter": reporter,
        "assignee_id": None,
        "assignee": None,
        "category_id": None,
        "building_id": uuid.uuid4(),
        "floor_id": None,
        "seat_id": None,
        "created_at": NOW,
        "updated_at": NOW,
    }
    values.update(kw)
    return Incident(**values)


class TestUpdateModel:
    """PUT is a partial update: omitted, null and a value are three states."""

    def test_the_catalog_found_the_update_schemas(self) -> None:
        """Guards the parametrised tests below against silently testing nothing."""
        names = {m.__name__ for m in update_models()}
        assert {"IncidentUpdate", "BuildingUpdate", "AdminUpdateUserRequest"} <= names

    @pytest.mark.parametrize("model", update_models(), ids=lambda m: m.__name__)
    def test_clearable_names_real_fields(self, model: type[UpdateModel]) -> None:
        """A typo in CLEARABLE would silently make the intended field un-clearable."""
        assert model.CLEARABLE <= set(model.model_fields)

    @pytest.mark.parametrize("model", update_models(), ids=lambda m: m.__name__)
    def test_null_is_refused_on_every_non_clearable_field(self, model: type[UpdateModel]) -> None:
        """Otherwise a null reaches a NOT NULL column and surfaces as a 500."""
        for field in set(model.model_fields) - model.CLEARABLE:
            with pytest.raises(ValidationError) as exc:
                model.model_validate({field: None})
            assert error_fields(exc.value) == {field}

    @pytest.mark.parametrize("model", update_models(), ids=lambda m: m.__name__)
    def test_null_clears_every_clearable_field(self, model: type[UpdateModel]) -> None:
        for field in model.CLEARABLE:
            assert model.model_validate({field: None}).changes() == {field: None}

    @pytest.mark.parametrize("model", update_models(), ids=lambda m: m.__name__)
    def test_an_empty_body_changes_nothing(self, model: type[UpdateModel]) -> None:
        assert model.model_validate({}).changes() == {}

    def test_changes_carries_only_what_was_sent(self) -> None:
        req = schemas.IncidentUpdate(title="New title", assignee_id=None)
        assert req.changes() == {"title": "New title", "assignee_id": None}

    def test_values_are_still_validated(self) -> None:
        with pytest.raises(ValidationError):
            schemas.IncidentUpdate(title="")

    def test_the_null_message_says_what_to_do(self) -> None:
        with pytest.raises(ValidationError, match="omit the field"):
            schemas.IncidentUpdate(title=None)


class TestAdminUserSchemas:
    def _create(self, **kw: object) -> schemas.AdminCreateUserRequest:
        payload: dict[str, object] = {
            "email": "sam@acme.inc",
            "password": VALID_PASSWORD,
            "full_name": "Sam Lee",
            "role": Role.EMPLOYEE,
            "date_of_birth": "1990-05-05",
            **kw,
        }
        # An Employee needs an occupation; give one unless the test is about it.
        if payload["role"] is Role.EMPLOYEE:
            payload.setdefault("occupation", "Designer")
        return schemas.AdminCreateUserRequest(**payload)  # type: ignore[arg-type]

    @pytest.mark.parametrize("email", ["sam@gmail.com", "sam@acme.inc.evil.com"])
    def test_create_enforces_the_company_domain(self, email: str) -> None:
        """D5: admins get no exemption from the domain rule."""
        with pytest.raises(ValidationError, match="acme.inc"):
            self._create(email=email)

    def test_create_normalises_the_email(self) -> None:
        assert self._create(email="  Sam@ACME.inc ").email == "sam@acme.inc"

    def test_an_engineer_needs_a_specialty(self) -> None:
        with pytest.raises(ValidationError, match="specialty is required"):
            self._create(role=Role.ENGINEER)

    def test_an_engineer_with_a_specialty_is_accepted(self) -> None:
        assert self._create(role=Role.ENGINEER, specialty="HVAC").specialty == "HVAC"

    @pytest.mark.parametrize("role", [Role.EMPLOYEE, Role.FACILITY_ADMIN])
    def test_only_an_engineer_may_have_a_specialty(self, role: Role) -> None:
        """Rejected rather than dropped, so the client sees its mistake."""
        with pytest.raises(ValidationError, match="applies only to an Engineer"):
            self._create(role=role, specialty="HVAC")

    def test_update_accepts_a_specialty(self) -> None:
        req = schemas.AdminUpdateUserRequest(role=Role.ENGINEER, specialty="Electrical")
        assert req.changes() == {"role": Role.ENGINEER, "specialty": "Electrical"}

    def test_user_filters_sort_is_an_allowlist(self) -> None:
        with pytest.raises(ValidationError):
            schemas.UserFilters(sort="password_hash")

    @pytest.mark.parametrize("sort", ["created_at", "email", "full_name", "role"])
    def test_user_filters_permitted_sorts(self, sort: str) -> None:
        assert schemas.UserFilters(sort=sort).sort == sort


class TestPasswordChange:
    def test_accepts_a_valid_change(self) -> None:
        req = schemas.ChangePasswordRequest(current_password="old", new_password=VALID_PASSWORD)
        assert req.new_password == VALID_PASSWORD

    def test_the_new_password_meets_the_strength_rule(self) -> None:
        with pytest.raises(ValidationError):
            schemas.ChangePasswordRequest(current_password="old", new_password="short")

    def test_the_current_password_is_not_held_to_the_new_rule(self) -> None:
        """A policy tightened later must not stop a user from changing a weak one."""
        assert schemas.ChangePasswordRequest(current_password="x", new_password=VALID_PASSWORD)

    def test_a_no_op_change_is_refused(self) -> None:
        """It would still revoke every session, to no purpose."""
        with pytest.raises(ValidationError, match="must differ"):
            schemas.ChangePasswordRequest(
                current_password=VALID_PASSWORD, new_password=VALID_PASSWORD
            )


class TestUserShapes:
    def test_summary_carries_no_email(self) -> None:
        """Embedded wherever a user appears; an address is not every viewer's business."""
        assert "email" not in schemas.UserSummary.model_fields

    def test_me_carries_an_engineer_profile(self) -> None:
        assert "engineer_profile" in schemas.MeOut.model_fields

    def test_me_profile_is_null_for_non_engineers(self) -> None:
        me = schemas.MeOut.model_validate(
            {
                "id": uuid.uuid4(),
                "email": "jane@acme.inc",
                "full_name": "Jane Doe",
                "role": Role.EMPLOYEE,
                "occupation": "Analyst",
                "date_of_birth": "1990-01-01",
                "is_active": True,
                "created_at": NOW,
                "engineer_profile": None,
            }
        )
        assert me.engineer_profile is None

    def test_register_response_is_only_a_message(self) -> None:
        """Returning the user would confirm whether the address was new."""
        assert set(schemas.RegisterAccepted.model_fields) == {"message"}


class TestFacilitySchemas:
    @pytest.mark.parametrize(
        ("model", "good", "default"),
        [
            (schemas.BuildingFilters, ["code", "name", "created_at"], "code"),
            (schemas.FloorFilters, ["level", "name"], "level"),
            (schemas.SeatFilters, ["code", "label"], "code"),
            (schemas.CategoryFilters, ["name"], "name"),
        ],
        ids=lambda v: getattr(v, "__name__", None),
    )
    def test_sorts_are_allowlists(self, model: type, good: list[str], default: str) -> None:
        assert model().sort == default
        assert model().order == "asc"
        for sort in good:
            assert model(sort=sort).sort == sort
        with pytest.raises(ValidationError):
            model(sort="id; DROP TABLE buildings")

    def test_inactive_records_are_hidden_by_default(self) -> None:
        assert schemas.BuildingFilters().include_inactive is False

    def test_roots_only_and_parent_cannot_combine(self) -> None:
        with pytest.raises(ValidationError, match="cannot be combined"):
            schemas.CategoryFilters(roots_only=True, parent_id=uuid.uuid4())

    def test_building_code_cannot_be_renamed(self) -> None:
        """It is printed on signage and asset tags."""
        assert "code" not in schemas.BuildingUpdate.model_fields

    def test_floors_and_seats_cannot_change_parent(self) -> None:
        assert "building_id" not in schemas.FloorUpdate.model_fields
        assert "floor_id" not in schemas.SeatUpdate.model_fields

    def test_categories_cannot_be_reparented(self) -> None:
        assert "parent_id" not in schemas.CategoryUpdate.model_fields


class TestEngineerSchemas:
    @pytest.mark.parametrize("value", [0, 51])
    def test_concurrency_limit_is_bounded(self, value: int) -> None:
        with pytest.raises(ValidationError):
            schemas.EngineerProfileUpdate(max_concurrent_incidents=value)

    def test_engineer_out_embeds_the_user_and_load(self) -> None:
        engineer = user(Role.ENGINEER, "Sam Lee")
        out = schemas.EngineerOut.model_validate(
            {
                "user_id": engineer.id,
                "specialty": "HVAC",
                "max_concurrent_incidents": 5,
                "is_available": True,
                "user": engineer,
                "open_assignments": 2,
            }
        )
        assert (out.user.full_name, out.open_assignments) == ("Sam Lee", 2)

    def test_engineer_filter_sort_is_an_allowlist(self) -> None:
        with pytest.raises(ValidationError):
            schemas.EngineerFilters(sort="password_hash")


class TestIncidentShapes:
    def test_incident_embeds_reporter_and_assignee(self) -> None:
        """An employee cannot call /users, so an id alone is unrenderable."""
        engineer = user(Role.ENGINEER, "Sam Lee")
        row = incident(assignee=engineer, assignee_id=engineer.id)
        out = schemas.IncidentOut.model_validate(row)
        assert out.reporter.full_name == "Jane Doe"
        assert out.assignee is not None and out.assignee.full_name == "Sam Lee"

    def test_unassigned_incident_has_a_null_assignee(self) -> None:
        assert schemas.IncidentOut.model_validate(incident()).assignee is None

    def test_embedded_users_never_carry_an_email(self) -> None:
        body = schemas.IncidentOut.model_validate(incident()).model_dump()
        assert "email" not in body["reporter"]

    def test_detail_lists_the_callers_actions(self) -> None:
        """Built from the same function the transition endpoint validates with."""
        engineer = user(Role.ENGINEER)
        row = incident(
            status=IncidentStatus.IN_PROGRESS, assignee=engineer, assignee_id=engineer.id
        )
        context = workflow.TransitionContext(
            current=row.status,
            actor_id=engineer.id,
            actor_role=engineer.role,
            reporter_id=row.reporter_id,
            assignee_id=row.assignee_id,
        )
        by_target = {
            rule.target: rule for rule in workflow.TRANSITIONS if rule.source is row.status
        }
        options = [
            {
                "to": target,
                "label": by_target[target].label,
                "requires": sorted(by_target[target].required_payload),
            }
            for target in workflow.allowed_targets(
                context, {"resolution_note": "x", "blocked_reason": "x"}
            )
        ]
        detail = schemas.IncidentDetailOut.model_validate(
            {**schemas.IncidentOut.model_validate(row).model_dump(), "allowed_transitions": options}
        )
        assert {o.to for o in detail.allowed_transitions} == {
            IncidentStatus.BLOCKED,
            IncidentStatus.RESOLVED,
        }

    def test_note_embeds_its_author(self) -> None:
        author = user(Role.ENGINEER, "Sam Lee")
        note = IncidentNote(
            id=uuid.uuid4(),
            incident_id=uuid.uuid4(),
            author_id=author.id,
            author=author,
            body="Ordered the part.",
            visibility=NoteVisibility.INTERNAL,
            created_at=NOW,
        )
        assert schemas.NoteOut.model_validate(note).author.full_name == "Sam Lee"

    def test_history_embeds_its_actor(self) -> None:
        actor = user(Role.FACILITY_ADMIN, "Ada Admin")
        row = IncidentStatusHistory(
            id=uuid.uuid4(),
            incident_id=uuid.uuid4(),
            from_status=None,
            to_status=IncidentStatus.OPEN,
            actor_id=actor.id,
            actor=actor,
            note=None,
            created_at=NOW,
        )
        assert schemas.StatusHistoryOut.model_validate(row).actor.role is Role.FACILITY_ADMIN

    def test_incident_filters_accept_a_category(self) -> None:
        category = uuid.uuid4()
        assert schemas.IncidentFilters(category_id=category).category_id == category

    def test_timeline_reads_oldest_first(self) -> None:
        assert schemas.TimelineParams().order == "asc"


class TestWorkflowOut:
    def test_round_trips_describe_exactly(self) -> None:
        """The endpoint validates describe() through this and must emit it unchanged."""
        described = workflow.describe()
        out = schemas.WorkflowOut.model_validate(described)
        assert out.model_dump(mode="json", by_alias=True) == described

    def test_the_wire_name_is_from(self) -> None:
        out = schemas.WorkflowOut.model_validate(workflow.describe())
        dumped = out.model_dump(by_alias=True)["transitions"][0]
        assert "from" in dumped and "source" not in dumped


class TestEscalations:
    @pytest.mark.parametrize("decision", [EscalationStatus.APPROVED, EscalationStatus.REJECTED])
    def test_a_verdict_is_accepted(self, decision: EscalationStatus) -> None:
        assert schemas.EscalationDecision(decision=decision).decision is decision

    def test_pending_is_not_a_decision(self) -> None:
        with pytest.raises(ValidationError, match="Approved or Rejected"):
            schemas.EscalationDecision(decision=EscalationStatus.PENDING)

    def test_the_decision_is_not_called_status(self) -> None:
        """`status` is server-controlled; the mass-assignment test would refuse it."""
        assert "status" not in schemas.EscalationDecision.model_fields

    def test_the_queue_defaults_to_pending_oldest_first(self) -> None:
        filters = schemas.EscalationFilters()
        assert (filters.status, filters.order) == (EscalationStatus.PENDING, "asc")

    def test_a_reason_is_required(self) -> None:
        with pytest.raises(ValidationError):
            schemas.EscalationCreate(reason="  ")

    def test_out_embeds_requester_and_decider(self) -> None:
        requester, admin = user(), user(Role.FACILITY_ADMIN, "Ada Admin")
        parent = incident(title="Flooded row", priority=Priority.HIGH)
        row = EscalationRequest(
            id=uuid.uuid4(),
            incident_id=parent.id,
            incident=parent,
            requested_by_id=requester.id,
            requested_by=requester,
            reason="Flooding",
            status=EscalationStatus.APPROVED,
            decided_by_id=admin.id,
            decided_by=admin,
            decided_at=NOW,
            decision_note=None,
            created_at=NOW,
        )
        out = schemas.EscalationOut.model_validate(row)
        assert out.decided_by is not None and out.decided_by.full_name == "Ada Admin"
        # The incident's facts ride along for the queue, read through the relationship.
        assert (out.incident_title, out.incident_status, out.incident_priority) == (
            "Flooded row", IncidentStatus.OPEN, Priority.HIGH
        )


class TestReportRange:
    def test_defaults_to_the_last_thirty_days(self) -> None:
        window = schemas.ReportRange()
        assert window.date_to == dt.datetime.now(dt.UTC).date()
        assert window.date_from is not None and window.date_to is not None
        assert (window.date_to - window.date_from).days + 1 == DEFAULT_RANGE_DAYS

    def test_accepts_the_wire_names(self) -> None:
        window = schemas.ReportRange.model_validate({"from": "2026-01-01", "to": "2026-01-31"})
        assert (window.date_from, window.date_to) == (dt.date(2026, 1, 1), dt.date(2026, 1, 31))

    def test_a_backwards_range_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="must not be after"):
            schemas.ReportRange.model_validate({"from": "2026-02-01", "to": "2026-01-01"})

    def test_the_maximum_range_is_accepted(self) -> None:
        start = dt.date(2025, 1, 1)
        end = start + dt.timedelta(days=MAX_RANGE_DAYS - 1)
        assert schemas.ReportRange.model_validate({"from": start, "to": end})

    def test_one_day_more_is_refused(self) -> None:
        start = dt.date(2025, 1, 1)
        end = start + dt.timedelta(days=MAX_RANGE_DAYS)
        with pytest.raises(ValidationError, match="at most"):
            schemas.ReportRange.model_validate({"from": start, "to": end})

    def test_unknown_parameters_are_refused(self) -> None:
        with pytest.raises(ValidationError):
            schemas.ReportRange.model_validate({"since": "2026-01-01"})

    @pytest.mark.parametrize(
        ("model", "field", "bad"),
        [
            (schemas.SlaParams, "group_by", "assignee"),
            (schemas.VolumeParams, "interval", "hour"),
            (schemas.VolumeParams, "group_by", "reporter"),
        ],
    )
    def test_grouping_is_an_allowlist(self, model: type, field: str, bad: str) -> None:
        with pytest.raises(ValidationError):
            model.model_validate({field: bad})

    def test_reports_echo_the_window_under_the_wire_names(self) -> None:
        report = schemas.VolumeReport.model_validate(
            {
                "from": "2026-01-01",
                "to": "2026-01-31",
                "interval": "day",
                "group_by": "status",
                "rows": [],
            }
        )
        assert {"from", "to"} <= set(report.model_dump(by_alias=True))


class TestSlaTargets:
    def test_every_priority_has_a_target(self) -> None:
        assert set(SLA_TARGETS) == set(Priority)

    def test_more_urgent_means_a_tighter_target(self) -> None:
        order = [Priority.CRITICAL, Priority.HIGH, Priority.MEDIUM, Priority.LOW]
        targets = [SLA_TARGETS[p] for p in order]
        assert targets == sorted(targets)


class TestDateOfBirth:
    """Required for every user, and nobody is born after today."""

    TODAY = dt.datetime.now(dt.UTC).date()

    def _register(self, born: object) -> schemas.RegisterRequest:
        return schemas.RegisterRequest(
            email="new@acme.inc",
            password=VALID_PASSWORD,
            full_name="New",
            occupation="Analyst",
            date_of_birth=born,  # type: ignore[arg-type]
        )

    def test_today_is_accepted(self) -> None:
        assert self._register(self.TODAY).date_of_birth == self.TODAY

    def test_tomorrow_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="cannot be in the future") as exc:
            self._register(self.TODAY + dt.timedelta(days=1))
        assert error_fields(exc.value) == {"date_of_birth"}

    def test_a_mistyped_ancient_year_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="cannot be before 1900-01-01"):
            self._register("0985-06-01")

    def test_the_earliest_permitted_date_is_accepted(self) -> None:
        assert self._register("1900-01-01")

    def test_it_is_required_at_registration(self) -> None:
        with pytest.raises(ValidationError) as exc:
            schemas.RegisterRequest(
                email="new@acme.inc", password=VALID_PASSWORD, full_name="N", occupation="A"
            )
        assert "date_of_birth" in error_fields(exc.value)

    @pytest.mark.parametrize("role", list(Role))
    def test_it_is_required_for_every_role_on_admin_create(self, role: Role) -> None:
        extra = {"specialty": "HVAC"} if role is Role.ENGINEER else {}
        if role is Role.EMPLOYEE:
            extra["occupation"] = "Analyst"
        with pytest.raises(ValidationError) as exc:
            schemas.AdminCreateUserRequest(
                email="x@acme.inc", password=VALID_PASSWORD, full_name="X", role=role, **extra
            )
        assert "date_of_birth" in error_fields(exc.value)

    def test_the_future_rule_applies_to_updates_too(self) -> None:
        with pytest.raises(ValidationError, match="cannot be in the future"):
            schemas.AdminUpdateUserRequest(date_of_birth=self.TODAY + dt.timedelta(days=1))

    def test_an_update_may_correct_it(self) -> None:
        req = schemas.AdminUpdateUserRequest(date_of_birth="1991-02-03")
        assert req.changes() == {"date_of_birth": dt.date(1991, 2, 3)}


class TestOccupation:
    """Required for an Employee, refused for every other role."""

    def test_registration_requires_it(self) -> None:
        with pytest.raises(ValidationError) as exc:
            schemas.RegisterRequest(
                email="new@acme.inc",
                password=VALID_PASSWORD,
                full_name="N",
                date_of_birth="1990-01-01",
            )
        assert "occupation" in error_fields(exc.value)

    def test_admin_create_requires_it_for_an_employee(self) -> None:
        with pytest.raises(ValidationError, match="occupation is required for an Employee"):
            schemas.AdminCreateUserRequest(
                email="x@acme.inc",
                password=VALID_PASSWORD,
                full_name="X",
                role=Role.EMPLOYEE,
                date_of_birth="1990-01-01",
            )

    @pytest.mark.parametrize("role", [Role.ENGINEER, Role.FACILITY_ADMIN])
    def test_admin_create_refuses_it_for_other_roles(self, role: Role) -> None:
        extra = {"specialty": "HVAC"} if role is Role.ENGINEER else {}
        with pytest.raises(ValidationError, match="applies only to an Employee"):
            schemas.AdminCreateUserRequest(
                email="x@acme.inc",
                password=VALID_PASSWORD,
                full_name="X",
                role=role,
                date_of_birth="1990-01-01",
                occupation="Analyst",
                **extra,
            )

    def test_it_cannot_be_blank(self) -> None:
        with pytest.raises(ValidationError):
            schemas.RegisterRequest(
                email="new@acme.inc",
                password=VALID_PASSWORD,
                full_name="N",
                occupation="   ",
                date_of_birth="1990-01-01",
            )

    def test_users_expose_both_fields(self) -> None:
        assert {"occupation", "date_of_birth"} <= set(schemas.UserOut.model_fields)

    def test_summaries_expose_neither(self) -> None:
        """A birth date is personal data; summaries are shown to every viewer."""
        assert not {"occupation", "date_of_birth"} & set(schemas.UserSummary.model_fields)


class TestFindByEmail:
    def test_the_email_filter_is_normalised(self) -> None:
        """So an admin pasting `Jane@ACME.inc ` still finds jane@acme.inc."""
        assert schemas.UserFilters(email="  Jane@ACME.inc ").email == "jane@acme.inc"

    def test_it_is_optional(self) -> None:
        assert schemas.UserFilters().email is None
