"""The auth journey over real HTTP against a real server process.

Every request here crosses a process boundary and lands on a pooled server
connection; every assertion about the database opens a connection of its own.
Nothing is rolled back, so a green run means the writes genuinely committed --
the one property the savepoint fixture in the integration tier cannot show.

The steps follow plan.md T10: register -> login -> me -> refresh -> replay the
old refresh, then continue through the password change and logout that the
contract (api.md A3, A4, A7) adds on top.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Any

import httpx
import pytest

pytestmark = pytest.mark.e2e

P = "/api/auth"
PASSWORD = "correct-horse-battery-staple"
NEW_PASSWORD = "an-entirely-new-passphrase"

# The `user_row` fixture in conftest.py: a lookup by email over a new connection.
RowLookup = Callable[[str], dict[str, Any] | None]


def unique_email() -> str:
    return f"e2e.{uuid.uuid4().hex[:10]}@acme.inc"


def bearer(tokens: dict[str, Any] | str) -> dict[str, str]:
    token = tokens if isinstance(tokens, str) else tokens["access_token"]
    return {"Authorization": f"Bearer {token}"}


def register(client: httpx.Client, email: str, password: str = PASSWORD) -> httpx.Response:
    return client.post(
        f"{P}/register",
        json={
            "email": email,
            "password": password,
            "full_name": "End To End",
            "occupation": "Tester",
            "date_of_birth": "1991-06-15",
        },
    )


def login(client: httpx.Client, email: str, password: str = PASSWORD) -> dict[str, Any]:
    resp = client.post(f"{P}/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()


class TestServer:
    def test_identifies_itself(self, client: httpx.Client) -> None:
        resp = client.get(f"{P}/healthz")
        assert resp.status_code == 200
        body = resp.json()
        assert body["service"] == "auth"
        # "source" from a clean tree, a short sha once tools/sync-shared.sh has
        # stamped it; either way the build is identified.
        assert body["build"]["git_sha"]
        assert resp.headers["x-request-id"]

    def test_an_unauthenticated_request_carries_the_challenge(self, client: httpx.Client) -> None:
        resp = client.get(f"{P}/me")
        assert resp.status_code == 401
        assert resp.headers["www-authenticate"] == "Bearer"
        assert resp.json()["error"] == "unauthenticated"


class TestRegistration:
    def test_the_row_is_visible_on_a_new_connection(
        self, client: httpx.Client, user_row: RowLookup
    ) -> None:
        email = unique_email()
        assert user_row(email) is None
        resp = register(client, email)
        assert resp.status_code == 202, resp.text

        row = user_row(email)
        assert row is not None
        assert row["role"] == "Employee" and row["is_active"] is True
        assert PASSWORD not in row["password_hash"]

    def test_a_second_registration_changes_nothing(
        self, client: httpx.Client, user_row: RowLookup
    ) -> None:
        """The response is identical and the stored account is untouched."""
        email = unique_email()
        first = register(client, email)
        before = user_row(email)
        second = register(client, email, password="a-different-passphrase")
        assert (second.status_code, second.json()) == (first.status_code, first.json())
        assert user_row(email) == before
        # The original password still signs in; the impostor's does not.
        login(client, email)
        denied = client.post(
            f"{P}/login", json={"email": email, "password": "a-different-passphrase"}
        )
        assert denied.status_code == 401


class TestJourney:
    def test_register_login_me_refresh_and_replay(
        self, client: httpx.Client, user_row: RowLookup
    ) -> None:
        email = unique_email()
        assert register(client, email).status_code == 202
        first = login(client, email)
        assert first["token_type"] == "bearer" and first["expires_in"] == 1800

        me = client.get(f"{P}/me", headers=bearer(first))
        assert me.status_code == 200, me.text
        row = user_row(email)
        assert row is not None
        assert me.json()["id"] == str(row["id"])
        assert me.json()["email"] == email
        assert me.json()["role"] == "Employee"
        assert me.json()["engineer_profile"] is None

        # Rotation: the new pair works, and the presented token is spent.
        rotated = client.post(f"{P}/refresh", json={"refresh_token": first["refresh_token"]})
        assert rotated.status_code == 200, rotated.text
        second = rotated.json()
        assert second["refresh_token"] != first["refresh_token"]
        assert client.get(f"{P}/me", headers=bearer(second)).status_code == 200

        # Replay of the spent token: the whole family is revoked, so the pair
        # that rotation just issued dies with it (api.md A3).
        replay = client.post(f"{P}/refresh", json={"refresh_token": first["refresh_token"]})
        assert replay.status_code == 401
        assert replay.json()["error"] == "refresh_token_reused"
        assert replay.headers["www-authenticate"] == "Bearer"

        family = client.post(f"{P}/refresh", json={"refresh_token": second["refresh_token"]})
        assert family.status_code == 401
        assert family.json()["error"] == "refresh_token_reused"

        # An access token is the wrong kind of token here, and says so.
        wrong = client.post(f"{P}/refresh", json={"refresh_token": second["access_token"]})
        assert wrong.status_code == 401
        assert wrong.json()["error"] == "wrong_token_type"

        # A fresh login starts a fresh family, unaffected by the revoked one.
        third = login(client, email)
        assert client.get(f"{P}/me", headers=bearer(third)).status_code == 200

    def test_password_change_invalidates_every_earlier_session(
        self, client: httpx.Client, user_row: RowLookup
    ) -> None:
        email = unique_email()
        assert register(client, email).status_code == 202
        before = user_row(email)
        assert before is not None
        tokens = login(client, email)

        wrong = client.post(
            f"{P}/me/password",
            headers=bearer(tokens),
            json={"current_password": "not-the-password", "new_password": NEW_PASSWORD},
        )
        assert wrong.status_code == 400
        assert wrong.json()["details"][0]["field"] == "current_password"

        changed = client.post(
            f"{P}/me/password",
            headers=bearer(tokens),
            json={"current_password": PASSWORD, "new_password": NEW_PASSWORD},
        )
        assert changed.status_code == 204, changed.text

        after = user_row(email)
        assert after is not None
        assert after["password_hash"] != before["password_hash"]
        assert after["sessions_valid_from"] > before["sessions_valid_from"]

        # The access token predates sessions_valid_from; the refresh token is revoked.
        assert client.get(f"{P}/me", headers=bearer(tokens)).status_code == 401
        stale = client.post(f"{P}/refresh", json={"refresh_token": tokens["refresh_token"]})
        assert stale.status_code == 401

        # Only the new password signs in now.
        old = client.post(f"{P}/login", json={"email": email, "password": PASSWORD})
        assert old.status_code == 401
        login(client, email, NEW_PASSWORD)

    def test_logout_retires_the_device_and_logout_all_retires_the_user(
        self, client: httpx.Client
    ) -> None:
        email = unique_email()
        assert register(client, email).status_code == 202
        laptop = login(client, email)
        phone = login(client, email)

        # Logout needs no access token and retires only that family.
        out = client.post(f"{P}/logout", json={"refresh_token": laptop["refresh_token"]})
        assert out.status_code == 204
        retired = client.post(f"{P}/refresh", json={"refresh_token": laptop["refresh_token"]})
        assert retired.status_code == 401
        other = client.post(f"{P}/refresh", json={"refresh_token": phone["refresh_token"]})
        assert other.status_code == 200

        # An unknown token is not an oracle.
        assert client.post(f"{P}/logout", json={"refresh_token": "not-a-token"}).status_code == 204

        # Logout-all kills every outstanding access token on its next use.
        assert client.get(f"{P}/me", headers=bearer(phone)).status_code == 200
        assert client.post(f"{P}/logout-all", headers=bearer(phone)).status_code == 204
        assert client.get(f"{P}/me", headers=bearer(phone)).status_code == 401
        assert client.get(f"{P}/me", headers=bearer(laptop)).status_code == 401
