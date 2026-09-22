"""Token issuance and verification, including the classic JWT attacks."""

from __future__ import annotations

import datetime as dt
import uuid

import jwt
import pytest

from acme_core.exceptions import TokenExpired, Unauthenticated, WrongTokenType
from acme_core.security.tokens import (
    ALGORITHM,
    AUDIENCE,
    TokenType,
    decode_token,
    hash_refresh_token,
    issue_token,
)

pytestmark = pytest.mark.unit

SECRET = "a" * 64
OTHER_SECRET = "b" * 64
USER = uuid.UUID("66666666-6666-6666-6666-666666666666")


def access() -> str:
    return issue_token(USER, TokenType.ACCESS, SECRET)[0]


def refresh() -> str:
    return issue_token(USER, TokenType.REFRESH, SECRET)[0]


class TestRoundTrip:
    def test_subject_survives(self) -> None:
        assert decode_token(access(), SECRET).subject == USER

    def test_type_survives(self) -> None:
        assert decode_token(refresh(), SECRET).token_type is TokenType.REFRESH

    def test_each_token_has_a_unique_jti(self) -> None:
        """Needed to identify a rotation chain, and to blocklist one token."""
        assert decode_token(access(), SECRET).jti != decode_token(access(), SECRET).jti

    def test_claims_are_returned_at_issue_time(self) -> None:
        """So a caller can persist jti and expiry without decoding its own token."""
        token, claims = issue_token(USER, TokenType.REFRESH, SECRET)
        assert decode_token(token, SECRET).jti == claims.jti


class TestLifetimes:
    def test_access_tokens_are_short(self) -> None:
        _, claims = issue_token(USER, TokenType.ACCESS, SECRET)
        assert claims.expires_at - claims.issued_at == dt.timedelta(minutes=30)

    def test_refresh_tokens_are_long(self) -> None:
        _, claims = issue_token(USER, TokenType.REFRESH, SECRET)
        assert claims.expires_at - claims.issued_at == dt.timedelta(days=7)

    def test_skew_beyond_the_leeway_is_still_rejected(self) -> None:
        """Leeway is a tolerance, not a hole: an hour ahead is not drift."""
        far = dt.datetime.now(dt.UTC) + dt.timedelta(hours=1)
        token, _ = issue_token(USER, TokenType.ACCESS, SECRET, now=far)
        with pytest.raises(Unauthenticated):
            decode_token(token, SECRET)

    def test_an_expired_token_is_rejected_distinctly(self) -> None:
        """token_expired and unauthenticated call for different client behaviour."""
        past = dt.datetime.now(dt.UTC) - dt.timedelta(hours=2)
        token, _ = issue_token(USER, TokenType.ACCESS, SECRET, now=past)
        with pytest.raises(TokenExpired) as exc:
            decode_token(token, SECRET)
        assert exc.value.code == "token_expired"

    def test_a_token_from_the_future_is_still_usable(self) -> None:
        """Modest clock skew must not log people out.

        PyJWT rejects a future `iat` outright, so the leeway is what makes a
        Lambda a few seconds out of step survivable.
        """
        soon = dt.datetime.now(dt.UTC) + dt.timedelta(seconds=20)
        token, _ = issue_token(USER, TokenType.ACCESS, SECRET, now=soon)
        assert decode_token(token, SECRET).subject == USER


class TestTokenTypeSeparation:
    def test_a_refresh_token_is_rejected_at_a_protected_endpoint(self) -> None:
        """Otherwise a stolen 7-day token authenticates API calls for a week."""
        with pytest.raises(WrongTokenType) as exc:
            decode_token(refresh(), SECRET, expected_type=TokenType.ACCESS)
        assert exc.value.status == 401

    def test_an_access_token_is_rejected_at_refresh(self) -> None:
        """The other direction: a 30-minute token must not become a 7-day one."""
        with pytest.raises(WrongTokenType):
            decode_token(access(), SECRET, expected_type=TokenType.REFRESH)

    def test_each_type_is_accepted_at_its_own_endpoint(self) -> None:
        assert decode_token(access(), SECRET, expected_type=TokenType.ACCESS)
        assert decode_token(refresh(), SECRET, expected_type=TokenType.REFRESH)

    def test_a_missing_typ_claim_fails_closed(self) -> None:
        """Absent must be rejected, never defaulted to access."""
        forged = jwt.encode(
            {
                "sub": str(USER), "jti": str(uuid.uuid4()),
                "iat": int(dt.datetime.now(dt.UTC).timestamp()),
                "exp": int((dt.datetime.now(dt.UTC) + dt.timedelta(minutes=5)).timestamp()),
                "iss": "acme-auth-auth", "aud": AUDIENCE,
            },
            SECRET, algorithm=ALGORITHM,
        )
        with pytest.raises(Unauthenticated):
            decode_token(forged, SECRET)

    def test_an_unrecognised_typ_is_rejected(self) -> None:
        forged = jwt.encode(
            {
                "sub": str(USER), "typ": "superuser", "jti": str(uuid.uuid4()),
                "iat": int(dt.datetime.now(dt.UTC).timestamp()),
                "exp": int((dt.datetime.now(dt.UTC) + dt.timedelta(minutes=5)).timestamp()),
                "iss": "acme-auth-auth", "aud": AUDIENCE,
            },
            SECRET, algorithm=ALGORITHM,
        )
        with pytest.raises(Unauthenticated):
            decode_token(forged, SECRET)


class TestSignatureAttacks:
    def test_algorithm_is_never_taken_from_the_token(self) -> None:
        """The classic break: alg:none makes any payload verify."""
        forged = jwt.encode({"sub": str(USER), "typ": "access"}, key="", algorithm="none")
        with pytest.raises(Unauthenticated):
            decode_token(forged, SECRET)

    def test_a_different_algorithm_is_rejected(self) -> None:
        """HS512 with the same key must not be accepted where HS256 is expected."""
        forged = jwt.encode(
            {
                "sub": str(USER), "typ": "access", "jti": str(uuid.uuid4()),
                "iat": int(dt.datetime.now(dt.UTC).timestamp()),
                "exp": int((dt.datetime.now(dt.UTC) + dt.timedelta(minutes=5)).timestamp()),
                "iss": "acme-auth-auth", "aud": AUDIENCE,
            },
            SECRET, algorithm="HS512",
        )
        with pytest.raises(Unauthenticated):
            decode_token(forged, SECRET)

    def test_a_token_signed_with_another_key_is_rejected(self) -> None:
        token, _ = issue_token(USER, TokenType.ACCESS, OTHER_SECRET)
        with pytest.raises(Unauthenticated):
            decode_token(token, SECRET)

    def test_a_tampered_payload_is_rejected(self) -> None:
        header, _payload, signature = access().split(".")
        forged = f"{header}.eyJzdWIiOiAiYWRtaW4ifQ.{signature}"
        with pytest.raises(Unauthenticated):
            decode_token(forged, SECRET)

    @pytest.mark.parametrize(
        "garbage", ["", "not-a-token", "a.b.c", "....", "Bearer " + "x" * 40]
    )
    def test_malformed_input_is_rejected_not_crashed(self, garbage: str) -> None:
        with pytest.raises(Unauthenticated):
            decode_token(garbage, SECRET)


class TestClaimBinding:
    def test_a_wrong_audience_is_rejected(self) -> None:
        """Stops a token minted for something else being replayed here."""
        forged = jwt.encode(
            {
                "sub": str(USER), "typ": "access", "jti": str(uuid.uuid4()),
                "iat": int(dt.datetime.now(dt.UTC).timestamp()),
                "exp": int((dt.datetime.now(dt.UTC) + dt.timedelta(minutes=5)).timestamp()),
                "iss": "acme-auth-auth", "aud": "some-other-api",
            },
            SECRET, algorithm=ALGORITHM,
        )
        with pytest.raises(Unauthenticated):
            decode_token(forged, SECRET)

    def test_a_wrong_issuer_is_rejected(self) -> None:
        forged = jwt.encode(
            {
                "sub": str(USER), "typ": "access", "jti": str(uuid.uuid4()),
                "iat": int(dt.datetime.now(dt.UTC).timestamp()),
                "exp": int((dt.datetime.now(dt.UTC) + dt.timedelta(minutes=5)).timestamp()),
                "iss": "somebody-else", "aud": AUDIENCE,
            },
            SECRET, algorithm=ALGORITHM,
        )
        with pytest.raises(Unauthenticated):
            decode_token(forged, SECRET)

    def test_a_non_uuid_subject_is_rejected(self) -> None:
        forged = jwt.encode(
            {
                "sub": "'; DROP TABLE users; --", "typ": "access", "jti": str(uuid.uuid4()),
                "iat": int(dt.datetime.now(dt.UTC).timestamp()),
                "exp": int((dt.datetime.now(dt.UTC) + dt.timedelta(minutes=5)).timestamp()),
                "iss": "acme-auth-auth", "aud": AUDIENCE,
            },
            SECRET, algorithm=ALGORITHM,
        )
        with pytest.raises(Unauthenticated):
            decode_token(forged, SECRET)

    def test_iat_is_exposed_for_session_revocation(self) -> None:
        """Compared against users.sessions_valid_from to invalidate old tokens."""
        assert decode_token(access(), SECRET).issued_at_epoch > 0


class TestRefreshTokenStorage:
    def test_hash_is_stable(self) -> None:
        token = refresh()
        assert hash_refresh_token(token) == hash_refresh_token(token)

    def test_different_tokens_hash_differently(self) -> None:
        assert hash_refresh_token(refresh()) != hash_refresh_token(refresh())

    def test_the_token_is_not_recoverable_from_the_hash(self) -> None:
        """A database disclosure must not hand over usable credentials."""
        token = refresh()
        digest = hash_refresh_token(token)
        assert token not in digest
        assert len(digest) == 64
