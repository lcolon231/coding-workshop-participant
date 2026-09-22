"""The auth service end to end: real routes, real database, real tokens.

Each class is one user-facing flow. Persistence is asserted through
`verify_session`, which has its own identity map, so a change that never
reached PostgreSQL cannot read as applied (hazard 3).
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from acme_core.models import Building, Incident, IncidentStatus, RefreshToken, Role, User
from acme_core.security.secret import get_jwt_secret
from acme_core.security.tokens import TokenType, issue_token

pytestmark = pytest.mark.integration

P = "/api/auth"
NEW_PASSWORD = "an-entirely-new-passphrase"
GENERIC_LOGIN_FAILURE = "Invalid email or password, or the account is temporarily locked."


def bearer(tokens: dict[str, Any] | str) -> dict[str, str]:
    token = tokens if isinstance(tokens, str) else tokens["access_token"]
    return {"Authorization": f"Bearer {token}"}


def fresh(session: Session, user: User) -> User:
    """Re-read a user through a session with its own identity map."""
    found = session.get(User, user.id, populate_existing=True)
    assert found is not None
    return found


# --------------------------------------------------------------------------- register


class TestRegister:
    def _register(self, client: TestClient, **kw: Any) -> Any:
        body = {
            "email": "new.person@acme.inc",
            "password": "a-long-enough-passphrase",
            "full_name": "New Person",
            **kw,
        }
        return client.post(f"{P}/register", json=body)

    def test_creates_an_employee(self, auth_client: TestClient, verify_session: Session) -> None:
        resp = self._register(auth_client)
        assert resp.status_code == 202
        user = verify_session.execute(
            select(User).where(User.email == "new.person@acme.inc")
        ).scalar_one()
        assert user.role is Role.EMPLOYEE and user.is_active

    def test_a_taken_email_gets_the_identical_response(
        self, auth_client: TestClient, make_user: Any, verify_session: Session
    ) -> None:
        """No account enumeration: body and status match the new-account case."""
        make_user(email="taken@acme.inc")
        first = self._register(auth_client, email="fresh@acme.inc")
        second = self._register(auth_client, email="taken@acme.inc")
        assert (second.status_code, second.json()) == (first.status_code, first.json())
        count = verify_session.execute(
            select(func.count()).select_from(User).where(User.email == "taken@acme.inc")
        ).scalar_one()
        assert count == 1

    def test_the_taken_path_does_not_change_the_existing_account(
        self, auth_client: TestClient, make_user: Any, verify_session: Session
    ) -> None:
        existing = make_user(email="taken@acme.inc", full_name="Original")
        self._register(auth_client, email="taken@acme.inc", full_name="Impostor")
        assert fresh(verify_session, existing).full_name == "Original"

    def test_the_email_is_normalised(
        self, auth_client: TestClient, verify_session: Session
    ) -> None:
        self._register(auth_client, email="  Mixed.Case@ACME.INC ")
        assert verify_session.execute(
            select(User).where(User.email == "mixed.case@acme.inc")
        ).scalar_one()

    def test_supplying_a_role_is_refused(self, auth_client: TestClient) -> None:
        resp = self._register(auth_client, role="Facility Admin")
        assert resp.status_code == 400
        assert resp.json()["error"] == "validation_error"

    @pytest.mark.parametrize("email", ["x@gmail.com", "x@acme.inc.evil.com"])
    def test_other_domains_are_refused(self, auth_client: TestClient, email: str) -> None:
        resp = self._register(auth_client, email=email)
        assert resp.status_code == 400
        assert resp.json()["details"][0]["field"] == "email"

    def test_a_short_password_is_refused_without_echoing_it(self, auth_client: TestClient) -> None:
        resp = self._register(auth_client, password="short-pw")
        assert resp.status_code == 400
        assert resp.json()["details"][0]["field"] == "password"
        assert "short-pw" not in resp.text

    def test_a_password_over_72_bytes_is_refused(self, auth_client: TestClient) -> None:
        """30 emoji is 30 characters but 120 bytes: bcrypt would silently truncate it."""
        resp = self._register(auth_client, password="🔒" * 30)
        assert resp.status_code == 400


# --------------------------------------------------------------------------- login


class TestLogin:
    def test_returns_a_token_pair(self, auth_client: TestClient, make_user: Any) -> None:
        user = make_user()
        resp = auth_client.post(
            f"{P}/login", json={"email": user.email, "password": make_user.password}
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["token_type"] == "bearer" and body["expires_in"] == 1800
        assert body["access_token"] != body["refresh_token"]

    def test_the_email_is_case_insensitive(self, auth_client: TestClient, make_user: Any) -> None:
        user = make_user(email="case@acme.inc")
        resp = auth_client.post(
            f"{P}/login", json={"email": "CASE@acme.inc", "password": make_user.password}
        )
        assert resp.status_code == 200, user

    @pytest.mark.parametrize("scenario", ["wrong_password", "unknown_email", "inactive"])
    def test_every_failure_looks_the_same(
        self, auth_client: TestClient, make_user: Any, scenario: str
    ) -> None:
        user = make_user(is_active=scenario != "inactive")
        email = "nobody@acme.inc" if scenario == "unknown_email" else user.email
        password = "not-the-password" if scenario == "wrong_password" else make_user.password
        resp = auth_client.post(f"{P}/login", json={"email": email, "password": password})
        assert resp.status_code == 401
        assert resp.json()["error"] == "unauthenticated"
        assert resp.json()["message"] == GENERIC_LOGIN_FAILURE
        assert resp.headers["WWW-Authenticate"] == "Bearer"

    def test_five_failures_lock_the_account(
        self, auth_client: TestClient, make_user: Any, verify_session: Session
    ) -> None:
        user = make_user()
        for _ in range(5):
            auth_client.post(f"{P}/login", json={"email": user.email, "password": "wrong-password"})
        assert fresh(verify_session, user).locked_until is not None
        # Even the right password is refused while locked -- with the same message.
        resp = auth_client.post(
            f"{P}/login", json={"email": user.email, "password": make_user.password}
        )
        assert resp.status_code == 401
        assert resp.json()["message"] == GENERIC_LOGIN_FAILURE

    def test_failures_are_persisted_despite_the_401(
        self, auth_client: TestClient, make_user: Any, verify_session: Session
    ) -> None:
        """The request rolls back on error; the counter must not roll back with it."""
        user = make_user()
        auth_client.post(f"{P}/login", json={"email": user.email, "password": "wrong-password"})
        assert fresh(verify_session, user).failed_login_count == 1

    def test_success_resets_the_counter(
        self, auth_client: TestClient, make_user: Any, verify_session: Session
    ) -> None:
        user = make_user()
        auth_client.post(f"{P}/login", json={"email": user.email, "password": "wrong-password"})
        auth_client.post(f"{P}/login", json={"email": user.email, "password": make_user.password})
        assert fresh(verify_session, user).failed_login_count == 0

    def test_an_expired_lock_lets_the_user_back_in(
        self, auth_client: TestClient, make_user: Any
    ) -> None:
        past = dt.datetime.now(dt.UTC) - dt.timedelta(minutes=1)
        user = make_user(locked_until=past)
        resp = auth_client.post(
            f"{P}/login", json={"email": user.email, "password": make_user.password}
        )
        assert resp.status_code == 200


# --------------------------------------------------------------------------- refresh


class TestRefresh:
    def test_rotates_the_pair(self, auth_client: TestClient, make_user: Any, sign_in: Any) -> None:
        tokens = sign_in(make_user().email)
        resp = auth_client.post(f"{P}/refresh", json={"refresh_token": tokens["refresh_token"]})
        assert resp.status_code == 200
        rotated = resp.json()
        assert rotated["refresh_token"] != tokens["refresh_token"]
        assert auth_client.get(f"{P}/me", headers=bearer(rotated)).status_code == 200

    def test_stores_only_a_hash(
        self, make_user: Any, sign_in: Any, verify_session: Session
    ) -> None:
        tokens = sign_in(make_user().email)
        stored = verify_session.execute(select(RefreshToken.token_hash)).scalars().all()
        assert tokens["refresh_token"] not in stored

    def test_replaying_a_rotated_token_revokes_the_family(
        self, auth_client: TestClient, make_user: Any, sign_in: Any
    ) -> None:
        """The thief and the victim both hold descendants; both must die."""
        tokens = sign_in(make_user().email)
        rotated = auth_client.post(
            f"{P}/refresh", json={"refresh_token": tokens["refresh_token"]}
        ).json()

        replay = auth_client.post(f"{P}/refresh", json={"refresh_token": tokens["refresh_token"]})
        assert replay.status_code == 401
        assert replay.json()["error"] == "refresh_token_reused"

        descendant = auth_client.post(
            f"{P}/refresh", json={"refresh_token": rotated["refresh_token"]}
        )
        assert descendant.status_code == 401

    def test_an_access_token_is_refused(
        self, auth_client: TestClient, make_user: Any, sign_in: Any
    ) -> None:
        """Or a stolen 30-minute token becomes a 7-day one."""
        tokens = sign_in(make_user().email)
        resp = auth_client.post(f"{P}/refresh", json={"refresh_token": tokens["access_token"]})
        assert resp.status_code == 401
        assert resp.json()["error"] == "wrong_token_type"

    def test_garbage_is_refused(self, auth_client: TestClient) -> None:
        resp = auth_client.post(f"{P}/refresh", json={"refresh_token": "not-a-token"})
        assert (resp.status_code, resp.json()["error"]) == (401, "unauthenticated")

    def test_an_expired_refresh_token_says_sign_in(
        self, auth_client: TestClient, make_user: Any, db_session: Session
    ) -> None:
        """`token_expired` would tell the client to refresh -- which is what just failed."""
        user = make_user()
        token, _ = issue_token(
            user.id, TokenType.REFRESH, get_jwt_secret(db_session), lifetime_seconds=-60
        )
        resp = auth_client.post(f"{P}/refresh", json={"refresh_token": token})
        assert (resp.status_code, resp.json()["error"]) == (401, "unauthenticated")

    def test_a_deactivated_user_cannot_refresh(
        self, auth_client: TestClient, make_user: Any, sign_in: Any, db_session: Session
    ) -> None:
        user = make_user()
        tokens = sign_in(user.email)
        user.is_active = False
        db_session.commit()
        resp = auth_client.post(f"{P}/refresh", json={"refresh_token": tokens["refresh_token"]})
        assert resp.status_code == 401


# --------------------------------------------------------------------------- me


class TestMe:
    def test_returns_the_caller(
        self, auth_client: TestClient, make_user: Any, sign_in: Any
    ) -> None:
        user = make_user(full_name="Jane Doe")
        body = auth_client.get(f"{P}/me", headers=bearer(sign_in(user.email))).json()
        assert (body["email"], body["full_name"], body["role"]) == (
            user.email,
            "Jane Doe",
            "Employee",
        )
        assert body["engineer_profile"] is None
        assert "password_hash" not in body

    def test_an_engineer_sees_their_profile(
        self, auth_client: TestClient, make_user: Any, sign_in: Any
    ) -> None:
        user = make_user(Role.ENGINEER, specialty="HVAC")
        body = auth_client.get(f"{P}/me", headers=bearer(sign_in(user.email))).json()
        assert body["engineer_profile"]["specialty"] == "HVAC"

    def test_role_comes_from_the_database_not_the_token(
        self, auth_client: TestClient, make_user: Any, sign_in: Any, db_session: Session
    ) -> None:
        """S7: a token carries no authority of its own."""
        user = make_user()
        tokens = sign_in(user.email)
        user.role = Role.FACILITY_ADMIN
        db_session.commit()
        assert auth_client.get(f"{P}/me", headers=bearer(tokens)).json()["role"] == "Facility Admin"

    def test_a_refresh_token_is_refused(
        self, auth_client: TestClient, make_user: Any, sign_in: Any
    ) -> None:
        tokens = sign_in(make_user().email)
        resp = auth_client.get(f"{P}/me", headers=bearer(tokens["refresh_token"]))
        assert (resp.status_code, resp.json()["error"]) == (401, "wrong_token_type")

    def test_no_token_is_401_in_the_envelope(self, auth_client: TestClient) -> None:
        resp = auth_client.get(f"{P}/me")
        assert (resp.status_code, resp.json()["error"]) == (401, "unauthenticated")
        assert resp.headers["WWW-Authenticate"] == "Bearer"

    def test_an_expired_access_token_says_so(
        self, auth_client: TestClient, make_user: Any, db_session: Session
    ) -> None:
        """So the client knows to refresh rather than sign in."""
        user = make_user()
        token, _ = issue_token(
            user.id, TokenType.ACCESS, get_jwt_secret(db_session), lifetime_seconds=-60
        )
        resp = auth_client.get(f"{P}/me", headers=bearer(token))
        assert (resp.status_code, resp.json()["error"]) == (401, "token_expired")

    def test_a_deactivated_user_is_locked_out_immediately(
        self, auth_client: TestClient, make_user: Any, sign_in: Any, db_session: Session
    ) -> None:
        user = make_user()
        tokens = sign_in(user.email)
        user.is_active = False
        db_session.commit()
        assert auth_client.get(f"{P}/me", headers=bearer(tokens)).status_code == 401


# --------------------------------------------------------------------------- logout


class TestLogout:
    def test_ends_this_device(self, auth_client: TestClient, make_user: Any, sign_in: Any) -> None:
        tokens = sign_in(make_user().email)
        assert (
            auth_client.post(
                f"{P}/logout", json={"refresh_token": tokens["refresh_token"]}
            ).status_code
            == 204
        )
        resp = auth_client.post(f"{P}/refresh", json={"refresh_token": tokens["refresh_token"]})
        assert resp.status_code == 401

    def test_other_devices_survive(
        self, auth_client: TestClient, make_user: Any, sign_in: Any
    ) -> None:
        user = make_user()
        laptop, phone = sign_in(user.email), sign_in(user.email)
        auth_client.post(f"{P}/logout", json={"refresh_token": laptop["refresh_token"]})
        resp = auth_client.post(f"{P}/refresh", json={"refresh_token": phone["refresh_token"]})
        assert resp.status_code == 200

    def test_an_unknown_token_is_still_204(self, auth_client: TestClient) -> None:
        """Not an oracle for which tokens exist."""
        resp = auth_client.post(f"{P}/logout", json={"refresh_token": "whatever"})
        assert resp.status_code == 204


class TestLogoutAll:
    def test_kills_every_token(self, auth_client: TestClient, make_user: Any, sign_in: Any) -> None:
        user = make_user()
        laptop, phone = sign_in(user.email), sign_in(user.email)
        assert auth_client.post(f"{P}/logout-all", headers=bearer(laptop)).status_code == 204
        assert auth_client.get(f"{P}/me", headers=bearer(laptop)).status_code == 401
        assert auth_client.get(f"{P}/me", headers=bearer(phone)).status_code == 401
        resp = auth_client.post(f"{P}/refresh", json={"refresh_token": phone["refresh_token"]})
        assert resp.status_code == 401

    def test_signing_in_again_works_at_once(
        self, auth_client: TestClient, make_user: Any, sign_in: Any
    ) -> None:
        """A new token issued in the same second as the cutoff must not be born revoked."""
        user = make_user()
        auth_client.post(f"{P}/logout-all", headers=bearer(sign_in(user.email)))
        assert auth_client.get(f"{P}/me", headers=bearer(sign_in(user.email))).status_code == 200


# --------------------------------------------------------------------------- password


class TestChangePassword:
    def test_changes_it_and_ends_every_session(
        self, auth_client: TestClient, make_user: Any, sign_in: Any
    ) -> None:
        user = make_user()
        tokens = sign_in(user.email)
        resp = auth_client.post(
            f"{P}/me/password",
            json={"current_password": make_user.password, "new_password": NEW_PASSWORD},
            headers=bearer(tokens),
        )
        assert resp.status_code == 204
        assert auth_client.get(f"{P}/me", headers=bearer(tokens)).status_code == 401
        old = auth_client.post(
            f"{P}/login", json={"email": user.email, "password": make_user.password}
        )
        assert old.status_code == 401
        assert sign_in(user.email, NEW_PASSWORD)

    def test_a_wrong_current_password_is_a_field_error(
        self, auth_client: TestClient, make_user: Any, sign_in: Any
    ) -> None:
        tokens = sign_in(make_user().email)
        resp = auth_client.post(
            f"{P}/me/password",
            json={"current_password": "not-it-at-all", "new_password": NEW_PASSWORD},
            headers=bearer(tokens),
        )
        assert resp.status_code == 400
        assert resp.json()["details"] == [
            {"field": "current_password", "message": "Incorrect password."}
        ]

    def test_requires_authentication(self, auth_client: TestClient) -> None:
        resp = auth_client.post(
            f"{P}/me/password", json={"current_password": "x", "new_password": NEW_PASSWORD}
        )
        assert resp.status_code == 401


# --------------------------------------------------------------------------- admin users


@pytest.fixture
def admin(make_user: Any) -> User:
    return make_user(Role.FACILITY_ADMIN, full_name="Ada Admin")


@pytest.fixture
def admin_headers(admin: User, sign_in: Any) -> dict[str, str]:
    return bearer(sign_in(admin.email))


class TestUserAdminAccess:
    @pytest.mark.parametrize("role", [Role.EMPLOYEE, Role.ENGINEER])
    def test_non_admins_are_forbidden(
        self, auth_client: TestClient, make_user: Any, sign_in: Any, role: Role
    ) -> None:
        headers = bearer(sign_in(make_user(role).email))
        assert auth_client.get(f"{P}/users", headers=headers).status_code == 403

    def test_forbidden_does_not_depend_on_the_target_existing(
        self, auth_client: TestClient, make_user: Any, sign_in: Any, admin: User
    ) -> None:
        """The role gate runs before the lookup, so 403 confirms nothing."""
        headers = bearer(sign_in(make_user().email))
        real = auth_client.get(f"{P}/users/{admin.id}", headers=headers)
        fake = auth_client.get(f"{P}/users/00000000-0000-0000-0000-000000000000", headers=headers)
        assert real.status_code == fake.status_code == 403


class TestListUsers:
    def test_pages_with_a_total(
        self, auth_client: TestClient, make_user: Any, admin_headers: dict[str, str]
    ) -> None:
        for _ in range(3):
            make_user()
        body = auth_client.get(f"{P}/users?limit=2", headers=admin_headers).json()
        assert len(body["items"]) == 2
        assert body["total"] == 4  # three employees and the admin

    def test_filters_by_role(
        self, auth_client: TestClient, make_user: Any, admin_headers: dict[str, str]
    ) -> None:
        make_user(Role.ENGINEER)
        make_user()
        body = auth_client.get(f"{P}/users?role=Engineer", headers=admin_headers).json()
        assert [u["role"] for u in body["items"]] == ["Engineer"]

    def test_search_matches_name_or_email_and_escapes_wildcards(
        self, auth_client: TestClient, make_user: Any, admin_headers: dict[str, str]
    ) -> None:
        make_user(full_name="Findable Person")
        make_user(full_name="Someone Else")
        body = auth_client.get(f"{P}/users?search=findable", headers=admin_headers).json()
        assert [u["full_name"] for u in body["items"]] == ["Findable Person"]
        wildcard = auth_client.get(f"{P}/users?search=%25", headers=admin_headers).json()
        assert wildcard["total"] == 0

    def test_an_unknown_sort_is_refused(
        self, auth_client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        resp = auth_client.get(f"{P}/users?sort=password_hash", headers=admin_headers)
        assert resp.status_code == 400

    def test_an_unknown_query_parameter_is_refused(
        self, auth_client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        resp = auth_client.get(f"{P}/users?password_hash=x", headers=admin_headers)
        assert resp.status_code == 400


class TestCreateUser:
    def _body(self, **kw: Any) -> dict[str, Any]:
        return {
            "email": "sam@acme.inc",
            "password": "a-long-enough-passphrase",
            "full_name": "Sam Lee",
            "role": "Employee",
            **kw,
        }

    def test_creates_an_engineer_with_a_profile(
        self, auth_client: TestClient, admin_headers: dict[str, str], verify_session: Session
    ) -> None:
        resp = auth_client.post(
            f"{P}/users", json=self._body(role="Engineer", specialty="HVAC"), headers=admin_headers
        )
        assert resp.status_code == 201
        assert resp.headers["Location"] == f"/api/auth/users/{resp.json()['id']}"
        user = verify_session.get(User, resp.json()["id"])
        assert user is not None and user.engineer_profile is not None
        assert user.engineer_profile.specialty == "HVAC"

    def test_the_new_user_can_sign_in(
        self, auth_client: TestClient, admin_headers: dict[str, str], sign_in: Any
    ) -> None:
        auth_client.post(f"{P}/users", json=self._body(), headers=admin_headers)
        assert sign_in("sam@acme.inc", "a-long-enough-passphrase")

    def test_a_duplicate_email_is_a_conflict(
        self, auth_client: TestClient, make_user: Any, admin_headers: dict[str, str]
    ) -> None:
        make_user(email="sam@acme.inc")
        resp = auth_client.post(f"{P}/users", json=self._body(), headers=admin_headers)
        assert (resp.status_code, resp.json()["error"]) == (409, "conflict")

    def test_an_engineer_without_a_specialty_is_refused(
        self, auth_client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        resp = auth_client.post(
            f"{P}/users", json=self._body(role="Engineer"), headers=admin_headers
        )
        assert resp.status_code == 400


class TestGetUser:
    def test_returns_the_user(
        self, auth_client: TestClient, make_user: Any, admin_headers: dict[str, str]
    ) -> None:
        user = make_user(full_name="Jane Doe")
        body = auth_client.get(f"{P}/users/{user.id}", headers=admin_headers).json()
        assert body["full_name"] == "Jane Doe"

    def test_an_unknown_id_is_404(
        self, auth_client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        resp = auth_client.get(
            f"{P}/users/00000000-0000-0000-0000-000000000000", headers=admin_headers
        )
        assert (resp.status_code, resp.json()["error"]) == (404, "not_found")

    def test_a_malformed_id_is_400(
        self, auth_client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        assert auth_client.get(f"{P}/users/not-a-uuid", headers=admin_headers).status_code == 400


class TestUpdateUser:
    def test_renames(
        self,
        auth_client: TestClient,
        make_user: Any,
        admin_headers: dict[str, str],
        verify_session: Session,
    ) -> None:
        user = make_user()
        resp = auth_client.put(
            f"{P}/users/{user.id}", json={"full_name": "Renamed"}, headers=admin_headers
        )
        assert resp.status_code == 200
        assert fresh(verify_session, user).full_name == "Renamed"

    def test_a_role_change_ends_the_targets_sessions(
        self,
        auth_client: TestClient,
        make_user: Any,
        sign_in: Any,
        admin_headers: dict[str, str],
    ) -> None:
        """A demoted admin must lose access now, not in thirty minutes."""
        other_admin = make_user(Role.FACILITY_ADMIN)
        their_tokens = sign_in(other_admin.email)
        resp = auth_client.put(
            f"{P}/users/{other_admin.id}", json={"role": "Employee"}, headers=admin_headers
        )
        assert resp.status_code == 200
        assert auth_client.get(f"{P}/users", headers=bearer(their_tokens)).status_code == 401

    def test_promotion_to_engineer_needs_a_specialty(
        self, auth_client: TestClient, make_user: Any, admin_headers: dict[str, str]
    ) -> None:
        user = make_user()
        resp = auth_client.put(
            f"{P}/users/{user.id}", json={"role": "Engineer"}, headers=admin_headers
        )
        assert resp.status_code == 400
        assert resp.json()["details"][0]["field"] == "specialty"

    def test_promotion_with_a_specialty_creates_the_profile(
        self,
        auth_client: TestClient,
        make_user: Any,
        admin_headers: dict[str, str],
        verify_session: Session,
    ) -> None:
        user = make_user()
        resp = auth_client.put(
            f"{P}/users/{user.id}",
            json={"role": "Engineer", "specialty": "Electrical"},
            headers=admin_headers,
        )
        assert resp.status_code == 200
        assert fresh(verify_session, user).engineer_profile.specialty == "Electrical"  # type: ignore[union-attr]

    def test_a_specialty_for_a_non_engineer_is_refused(
        self, auth_client: TestClient, make_user: Any, admin_headers: dict[str, str]
    ) -> None:
        user = make_user()
        resp = auth_client.put(
            f"{P}/users/{user.id}", json={"specialty": "HVAC"}, headers=admin_headers
        )
        assert resp.status_code == 400

    def test_an_admin_cannot_demote_themselves(
        self, auth_client: TestClient, admin: User, admin_headers: dict[str, str]
    ) -> None:
        resp = auth_client.put(
            f"{P}/users/{admin.id}", json={"role": "Employee"}, headers=admin_headers
        )
        assert (resp.status_code, resp.json()["error"]) == (409, "conflict")

    def test_an_admin_cannot_deactivate_themselves(
        self, auth_client: TestClient, admin: User, admin_headers: dict[str, str]
    ) -> None:
        resp = auth_client.put(
            f"{P}/users/{admin.id}", json={"is_active": False}, headers=admin_headers
        )
        assert resp.status_code == 409

    def test_an_engineer_with_open_work_cannot_be_demoted(
        self,
        auth_client: TestClient,
        make_user: Any,
        admin_headers: dict[str, str],
        db_session: Session,
    ) -> None:
        """Their incidents would strand: nobody would hold assigned_engineer on them."""
        engineer = make_user(Role.ENGINEER)
        reporter = make_user()
        building = Building(code="HQ", name="Headquarters")
        db_session.add(building)
        db_session.flush()
        db_session.add(
            Incident(
                title="Leak",
                description="d",
                reporter_id=reporter.id,
                assignee_id=engineer.id,
                building_id=building.id,
                status=IncidentStatus.IN_PROGRESS,
            )
        )
        db_session.commit()
        resp = auth_client.put(
            f"{P}/users/{engineer.id}", json={"role": "Employee"}, headers=admin_headers
        )
        assert resp.status_code == 409
        assert "1 open assignment" in resp.json()["message"]

    def test_null_on_a_required_field_is_refused(
        self, auth_client: TestClient, make_user: Any, admin_headers: dict[str, str]
    ) -> None:
        user = make_user()
        resp = auth_client.put(
            f"{P}/users/{user.id}", json={"full_name": None}, headers=admin_headers
        )
        assert resp.status_code == 400
        assert resp.json()["details"][0]["field"] == "full_name"


class TestDeactivateUser:
    def test_soft_deletes(
        self,
        auth_client: TestClient,
        make_user: Any,
        admin_headers: dict[str, str],
        verify_session: Session,
    ) -> None:
        user = make_user()
        assert auth_client.delete(f"{P}/users/{user.id}", headers=admin_headers).status_code == 204
        row = fresh(verify_session, user)
        assert row.is_active is False  # the row, and its history, remain

    def test_the_user_can_no_longer_sign_in_or_use_old_tokens(
        self,
        auth_client: TestClient,
        make_user: Any,
        sign_in: Any,
        admin_headers: dict[str, str],
    ) -> None:
        user = make_user()
        tokens = sign_in(user.email)
        auth_client.delete(f"{P}/users/{user.id}", headers=admin_headers)
        assert auth_client.get(f"{P}/me", headers=bearer(tokens)).status_code == 401
        resp = auth_client.post(
            f"{P}/login", json={"email": user.email, "password": make_user.password}
        )
        assert resp.status_code == 401

    def test_is_idempotent(
        self, auth_client: TestClient, make_user: Any, admin_headers: dict[str, str]
    ) -> None:
        user = make_user()
        auth_client.delete(f"{P}/users/{user.id}", headers=admin_headers)
        assert auth_client.delete(f"{P}/users/{user.id}", headers=admin_headers).status_code == 204

    def test_an_admin_cannot_delete_themselves(
        self, auth_client: TestClient, admin: User, admin_headers: dict[str, str]
    ) -> None:
        assert auth_client.delete(f"{P}/users/{admin.id}", headers=admin_headers).status_code == 409

    def test_an_unknown_id_is_404(
        self, auth_client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        resp = auth_client.delete(
            f"{P}/users/00000000-0000-0000-0000-000000000000", headers=admin_headers
        )
        assert resp.status_code == 404


# --------------------------------------------------------------------------- contract


class TestRouteContract:
    """Every route requires authentication unless it is on this list."""

    PUBLIC = {
        ("GET", f"{P}/healthz"),
        ("GET", f"{P}/readyz"),
        ("POST", f"{P}/register"),
        ("POST", f"{P}/login"),
        ("POST", f"{P}/refresh"),
        ("POST", f"{P}/logout"),
    }

    def test_every_other_route_rejects_an_anonymous_caller(self, auth_client: TestClient) -> None:
        """A route added without the auth dependency fails here, not in production.

        Driven from the OpenAPI schema rather than `app.routes`, which nests
        included routers in this FastAPI version and so yields no paths.
        """
        schema = auth_client.get(f"{P}/openapi.json").json()
        checked = 0
        for path, operations in schema["paths"].items():
            for method in operations:
                if (method.upper(), path) in self.PUBLIC:
                    continue
                url = path.replace("{user_id}", "00000000-0000-0000-0000-000000000000")
                resp = auth_client.request(method.upper(), url, json={})
                assert resp.status_code == 401, f"{method.upper()} {path} -> {resp.status_code}"
                checked += 1
        assert checked == 8, "the protected-route count changed; update this test deliberately"

    def test_the_public_list_matches_reality(self, auth_client: TestClient) -> None:
        """A stale allowlist entry would silently exempt a future route of that name."""
        schema = auth_client.get(f"{P}/openapi.json").json()
        documented = {(m.upper(), p) for p, ops in schema["paths"].items() for m in ops}
        assert self.PUBLIC <= documented


# --------------------------------------------------------------------------- edges


class TestEdges:
    def test_a_valid_but_unissued_refresh_token_is_refused(
        self, auth_client: TestClient, make_user: Any, db_session: Session
    ) -> None:
        """Correctly signed, but no row backs it -- e.g. minted before a key rotation."""
        token, _ = issue_token(make_user().id, TokenType.REFRESH, get_jwt_secret(db_session))
        resp = auth_client.post(f"{P}/refresh", json={"refresh_token": token})
        assert (resp.status_code, resp.json()["error"]) == (401, "unauthenticated")

    def test_a_token_for_a_user_that_no_longer_exists_is_refused(
        self, auth_client: TestClient, db_session: Session
    ) -> None:
        token, _ = issue_token(uuid.uuid4(), TokenType.ACCESS, get_jwt_secret(db_session))
        resp = auth_client.get(f"{P}/me", headers=bearer(token))
        assert (resp.status_code, resp.json()["error"]) == (401, "unauthenticated")

    def test_filters_by_activity(
        self, auth_client: TestClient, make_user: Any, admin_headers: dict[str, str]
    ) -> None:
        make_user(is_active=False, full_name="Gone")
        body = auth_client.get(f"{P}/users?is_active=false", headers=admin_headers).json()
        assert [u["full_name"] for u in body["items"]] == ["Gone"]

    def test_updating_an_unknown_user_is_404(
        self, auth_client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        resp = auth_client.put(
            f"{P}/users/{uuid.uuid4()}", json={"full_name": "X"}, headers=admin_headers
        )
        assert resp.status_code == 404

    def test_an_engineers_specialty_can_be_changed(
        self,
        auth_client: TestClient,
        make_user: Any,
        admin_headers: dict[str, str],
        verify_session: Session,
    ) -> None:
        engineer = make_user(Role.ENGINEER, specialty="HVAC")
        resp = auth_client.put(
            f"{P}/users/{engineer.id}", json={"specialty": "Plumbing"}, headers=admin_headers
        )
        assert resp.status_code == 200
        assert fresh(verify_session, engineer).engineer_profile.specialty == "Plumbing"  # type: ignore[union-attr]

    def test_an_engineer_without_open_work_can_be_deactivated(
        self, auth_client: TestClient, make_user: Any, admin_headers: dict[str, str]
    ) -> None:
        engineer = make_user(Role.ENGINEER)
        assert (
            auth_client.delete(f"{P}/users/{engineer.id}", headers=admin_headers).status_code == 204
        )

    def test_losing_a_registration_race_still_looks_like_success(
        self,
        auth_client: TestClient,
        make_user: Any,
        monkeypatch: pytest.MonkeyPatch,
        verify_session: Session,
    ) -> None:
        """The existence check can pass and the insert still collide; the unique index decides."""
        from auth_service import repository

        make_user(email="racer@acme.inc")
        monkeypatch.setattr(repository, "get_user_by_email", lambda *_: None)
        resp = auth_client.post(
            f"{P}/register",
            json={
                "email": "racer@acme.inc",
                "password": "a-long-enough-passphrase",
                "full_name": "R",
            },
        )
        assert resp.status_code == 202
        count = verify_session.execute(
            select(func.count()).select_from(User).where(User.email == "racer@acme.inc")
        ).scalar_one()
        assert count == 1

    def test_losing_an_admin_create_race_is_a_conflict(
        self,
        auth_client: TestClient,
        make_user: Any,
        admin_headers: dict[str, str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from auth_service import repository

        make_user(email="racer@acme.inc")
        real = repository.get_user_by_email
        # Miss only the create path's pre-check; sign-in for the admin already happened.
        monkeypatch.setattr(
            repository,
            "get_user_by_email",
            lambda s, e: None if e == "racer@acme.inc" else real(s, e),
        )
        resp = auth_client.post(
            f"{P}/users",
            json={
                "email": "racer@acme.inc",
                "password": "a-long-enough-passphrase",
                "full_name": "R",
                "role": "Employee",
            },
            headers=admin_headers,
        )
        assert (resp.status_code, resp.json()["error"]) == (409, "conflict")

    def test_deactivating_and_reactivating_through_put(
        self, auth_client: TestClient, make_user: Any, sign_in: Any, admin_headers: dict[str, str]
    ) -> None:
        user = make_user()
        tokens = sign_in(user.email)
        off = auth_client.put(
            f"{P}/users/{user.id}", json={"is_active": False}, headers=admin_headers
        )
        assert off.json()["is_active"] is False
        assert auth_client.get(f"{P}/me", headers=bearer(tokens)).status_code == 401
        on = auth_client.put(
            f"{P}/users/{user.id}", json={"is_active": True}, headers=admin_headers
        )
        assert on.json()["is_active"] is True
        assert sign_in(user.email)

    def test_renaming_an_engineer_keeps_their_profile(
        self,
        auth_client: TestClient,
        make_user: Any,
        admin_headers: dict[str, str],
        verify_session: Session,
    ) -> None:
        engineer = make_user(Role.ENGINEER, specialty="HVAC")
        auth_client.put(
            f"{P}/users/{engineer.id}", json={"full_name": "New Name"}, headers=admin_headers
        )
        assert fresh(verify_session, engineer).engineer_profile.specialty == "HVAC"  # type: ignore[union-attr]
