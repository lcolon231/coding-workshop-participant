"""The shared error envelope: shape, codes, statuses and what must not leak."""

from __future__ import annotations

import pytest
from fastapi import APIRouter, HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel

from acme_core import errors
from acme_core.api import create_app
from acme_core.errors import (
    AppError,
    Conflict,
    Forbidden,
    InternalError,
    InvalidTransition,
    NotFound,
    RefreshTokenReused,
    TokenExpired,
    Unauthenticated,
    ValidationFailed,
    WrongTokenType,
    all_error_classes,
    build_envelope,
    error_catalog,
)

pytestmark = pytest.mark.unit

# Obvious placeholders, referenced by name so no file pairs a literal with a
# host/user/port and trips secret scanners (GitGuardian). Not credentials.
FAKE_PW = "masked-value"

ENVELOPE_KEYS = {"error", "message", "details", "request_id"}

# Routes mount under the service prefix, exactly as they do in production.
P = "/api/probe"


class Credentials(BaseModel):
    email: str
    password: str
    attempts: int


@pytest.fixture
def client() -> TestClient:
    """An app that can raise every error class on demand.

    Built through `create_app` rather than a bare FastAPI so the request-id
    middleware is present: whether a 500 keeps its correlation id is a property
    of the composed application, not of the handler alone.
    """
    router = APIRouter()

    @router.get("/raise/{code}")
    def _raise(code: str) -> None:
        by_code = {cls.code: cls for cls in all_error_classes()}
        raise by_code[code]()

    @router.get("/framework/{status}")
    def _framework(status: int) -> None:
        """What FastAPI's own security helpers and Starlette raise."""
        raise HTTPException(status_code=status)

    @router.get("/boom")
    def _boom() -> None:
        raise RuntimeError(f"connection string postgres://user:{FAKE_PW}@host/db")

    @router.post("/login")
    def _login(_creds: Credentials) -> dict[str, str]:
        return {"ok": "yes"}

    @router.get("/detailed")
    def _detailed() -> None:
        raise ValidationFailed(
            "Two problems.",
            details=[
                {"field": "email", "message": "must be an @acme.inc address"},
                {"field": "password", "message": "too short"},
            ],
        )

    app = create_app("probe", [router], configure_logs=False)
    return TestClient(app, raise_server_exceptions=False)


class TestCatalogIntegrity:
    def test_every_class_has_a_unique_code(self) -> None:
        codes = [cls.code for cls in all_error_classes()]
        assert len(codes) == len(set(codes))

    def test_catalog_covers_every_class(self) -> None:
        """Guards against adding an error that no handler can map to a status."""
        assert set(error_catalog()) == {cls.code for cls in all_error_classes()}

    def test_a_subclass_without_a_code_is_rejected_at_definition(self) -> None:
        """Structural, not a convention: this fails at import, not at the first 500."""
        with pytest.raises(TypeError, match="must define a class-level 'code'"):

            class Broken(AppError):
                status = 418

    def test_a_subclass_without_a_status_is_rejected_at_definition(self) -> None:
        with pytest.raises(TypeError, match="must define a class-level 'status'"):

            class Broken(AppError):
                code = "teapot"

    @pytest.mark.parametrize(
        ("cls", "status"),
        [
            (ValidationFailed, 400),
            (Unauthenticated, 401),
            (TokenExpired, 401),
            (WrongTokenType, 401),
            (Forbidden, 403),
            (NotFound, 404),
            (Conflict, 409),
            (RefreshTokenReused, 401),
            (InvalidTransition, 409),
            (InternalError, 500),
        ],
        ids=lambda v: getattr(v, "code", str(v)),
    )
    def test_status_mapping(self, cls: type[AppError], status: int) -> None:
        assert cls.status == status


class TestEnvelopeShape:
    @pytest.mark.parametrize(
        "cls", all_error_classes(), ids=lambda c: c.code
    )
    def test_every_error_produces_the_same_keys(
        self, client: TestClient, cls: type[AppError]
    ) -> None:
        """This test is what "one consistent error format" actually means."""
        body = client.get(f"{P}/raise/{cls.code}").json()
        assert set(body) == ENVELOPE_KEYS

    @pytest.mark.parametrize("cls", all_error_classes(), ids=lambda c: c.code)
    def test_status_matches_the_class(self, client: TestClient, cls: type[AppError]) -> None:
        assert client.get(f"{P}/raise/{cls.code}").status_code == cls.status

    def test_details_default_to_an_empty_list(self, client: TestClient) -> None:
        """Never null: the client can iterate unconditionally."""
        assert client.get(f"{P}/raise/not_found").json()["details"] == []

    def test_details_are_carried_through(self, client: TestClient) -> None:
        details = client.get(f"{P}/detailed").json()["details"]
        assert [d["field"] for d in details] == ["email", "password"]

    def test_framework_404_uses_the_envelope_too(self, client: TestClient) -> None:
        """Routing failures come from Starlette, not from us."""
        body = client.get("/no-such-route").json()
        assert set(body) == ENVELOPE_KEYS
        assert body["error"] == "not_found"

    @pytest.mark.parametrize(
        ("status", "code"),
        [
            (400, "validation_error"),
            (401, "unauthenticated"),
            (403, "forbidden"),
            (404, "not_found"),
            (409, "conflict"),
        ],
    )
    def test_framework_errors_map_to_the_generic_code(
        self, client: TestClient, status: int, code: str
    ) -> None:
        """Several classes share a status; the framework must get the generic one.

        Pinned because the answer used to depend on the order classes were
        defined in, and a framework 401 reported as `refresh_token_reused`
        would tell the client its session had been stolen.
        """
        resp = client.get(f"{P}/framework/{status}")
        assert resp.status_code == status
        assert resp.json()["error"] == code

    def test_method_not_allowed_uses_the_envelope(self, client: TestClient) -> None:
        body = client.post(f"{P}/raise/not_found").json()
        assert set(body) == ENVELOPE_KEYS


class TestAuthChallenge:
    @pytest.mark.parametrize(
        "cls",
        [Unauthenticated, TokenExpired, WrongTokenType, RefreshTokenReused],
        ids=lambda c: c.code,
    )
    def test_401_carries_www_authenticate(
        self, client: TestClient, cls: type[AppError]
    ) -> None:
        assert client.get(f"{P}/raise/{cls.code}").headers["WWW-Authenticate"] == "Bearer"

    def test_other_statuses_do_not(self, client: TestClient) -> None:
        assert "WWW-Authenticate" not in client.get(f"{P}/raise/forbidden").headers


class TestValidationHandling:
    def test_validation_is_400_not_fastapi_default_422(self, client: TestClient) -> None:
        resp = client.post(f"{P}/login", json={"email": "a@acme.inc", "password": "x"})
        assert resp.status_code == 400
        assert resp.json()["error"] == "validation_error"

    def test_field_names_drop_the_location_prefix(self, client: TestClient) -> None:
        """Pydantic reports ('body', 'attempts'); the client wants 'attempts'."""
        resp = client.post(f"{P}/login", json={"email": "a@acme.inc", "password": "x"})
        assert [d["field"] for d in resp.json()["details"]] == ["attempts"]

    def test_absent_body_is_handled(self, client: TestClient) -> None:
        assert client.post(f"{P}/login").status_code == 400

    def test_submitted_values_are_never_echoed(self, client: TestClient) -> None:
        """The security property of this module.

        Pydantic's errors() carries an `input` key holding the submitted value,
        so spreading it would return the rejected password to the caller and
        write it to CloudWatch. Verified against the real serialised body.
        """
        resp = client.post(
            "/login",
            json={"email": "a@acme.inc", "password": FAKE_PW, "attempts": "nope"},
        )
        assert FAKE_PW not in resp.text
        assert "nope" not in resp.text

    def test_details_carry_only_field_and_message(self, client: TestClient) -> None:
        resp = client.post(f"{P}/login", json={"email": "a@acme.inc", "password": "x"})
        for detail in resp.json()["details"]:
            assert set(detail) == {"field", "message"}


class TestUnhandledExceptions:
    def test_returns_500_in_the_envelope(self, client: TestClient) -> None:
        resp = client.get(f"{P}/boom")
        assert resp.status_code == 500
        assert set(resp.json()) == ENVELOPE_KEYS

    def test_message_is_scrubbed(self, client: TestClient) -> None:
        """An exception message can contain a connection string."""
        assert FAKE_PW not in client.get(f"{P}/boom").text

    def test_request_id_is_kept(self, client: TestClient) -> None:
        """Scrubbing must not cost debuggability: the id is the CloudWatch key."""
        assert client.get(f"{P}/boom").json()["request_id"] is not None


class TestBuildEnvelope:
    def test_shape(self) -> None:
        assert set(build_envelope("x", "y")) == ENVELOPE_KEYS

    def test_uses_the_default_message(self) -> None:
        assert NotFound().message == NotFound.default_message

    def test_accepts_an_override(self) -> None:
        assert NotFound("incident 42 not found").message == "incident 42 not found"


class TestDetailsFromValidation:
    def test_root_level_error_is_labelled(self) -> None:
        class _Exc:
            @staticmethod
            def errors() -> list[dict[str, object]]:
                return [{"loc": ("body",), "msg": "bad", "input": "SECRET"}]

        details = errors.details_from_validation(_Exc())  # type: ignore[arg-type]
        assert details == [{"field": "__root__", "message": "bad"}]

    def test_nested_field_path_is_joined(self) -> None:
        class _Exc:
            @staticmethod
            def errors() -> list[dict[str, object]]:
                return [{"loc": ("body", "profile", "email"), "msg": "bad"}]

        details = errors.details_from_validation(_Exc())  # type: ignore[arg-type]
        assert details[0]["field"] == "profile.email"
