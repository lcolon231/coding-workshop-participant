"""Password hashing, length limits and the timing property."""

from __future__ import annotations

import pytest

from acme_core.exceptions import ValidationFailed
from acme_core.security.passwords import (
    MAX_PASSWORD_BYTES,
    MIN_PASSWORD_LENGTH,
    hash_password,
    validate_password_strength,
    verify_password,
)

pytestmark = pytest.mark.unit

GOOD = "correct-horse-battery-staple"


class TestHashing:
    def test_produces_a_bcrypt_hash(self) -> None:
        assert hash_password(GOOD).startswith("$2b$")

    def test_verifies_its_own_hash(self) -> None:
        assert verify_password(GOOD, hash_password(GOOD)) is True

    def test_rejects_a_wrong_password(self) -> None:
        assert verify_password("not-the-password", hash_password(GOOD)) is False

    def test_is_salted(self) -> None:
        """Identical passwords must not produce identical hashes."""
        assert hash_password(GOOD) != hash_password(GOOD)

    def test_plaintext_never_appears_in_the_hash(self) -> None:
        assert GOOD not in hash_password(GOOD)


class TestLengthLimits:
    def test_rejects_a_short_password(self) -> None:
        with pytest.raises(ValidationFailed) as exc:
            hash_password("a" * (MIN_PASSWORD_LENGTH - 1))
        assert exc.value.details[0]["field"] == "password"

    def test_accepts_exactly_the_minimum(self) -> None:
        validate_password_strength("a" * MIN_PASSWORD_LENGTH)

    def test_rejects_rather_than_truncates_a_long_password(self) -> None:
        """Truncating would make "A"*72 + anything authenticate identically."""
        with pytest.raises(ValidationFailed):
            hash_password("a" * (MAX_PASSWORD_BYTES + 1))

    def test_accepts_exactly_the_byte_limit(self) -> None:
        validate_password_strength("a" * MAX_PASSWORD_BYTES)

    def test_limit_is_bytes_not_characters(self) -> None:
        """A 30-character CJK password is 90 bytes and would be truncated."""
        password = "密码" * 15  # 30 characters, 90 UTF-8 bytes
        assert len(password) < MAX_PASSWORD_BYTES < len(password.encode("utf-8"))
        with pytest.raises(ValidationFailed):
            validate_password_strength(password)

    def test_a_long_passphrase_is_not_silently_equal_to_its_prefix(self) -> None:
        """The property rejection buys: distinct long passwords stay distinct."""
        base = "a" * MAX_PASSWORD_BYTES
        stored = hash_password(base)
        assert verify_password(base + "-extra", stored) is True  # truncated by bcrypt
        with pytest.raises(ValidationFailed):
            hash_password(base + "-extra")  # ...which is why we never store one


class TestNonEnumeration:
    def test_a_missing_hash_verifies_as_false(self) -> None:
        assert verify_password(GOOD, None) is False

    def test_a_missing_hash_still_runs_bcrypt(self) -> None:
        """Skipping the comparison would make "no such user" ~300ms faster.

        Measured rather than asserted structurally: the dummy comparison is the
        only thing making an unknown email indistinguishable from a wrong
        password.
        """
        import time

        stored = hash_password(GOOD)
        start = time.perf_counter()
        verify_password("attempt", None)
        missing = time.perf_counter() - start
        start = time.perf_counter()
        verify_password("attempt", stored)
        present = time.perf_counter() - start
        assert missing > present / 4

    def test_a_corrupt_hash_returns_false_rather_than_raising(self) -> None:
        """A truncated row is a failed login, not a 500."""
        assert verify_password(GOOD, "not-a-bcrypt-hash") is False

    def test_an_empty_hash_returns_false(self) -> None:
        assert verify_password(GOOD, "") is False
