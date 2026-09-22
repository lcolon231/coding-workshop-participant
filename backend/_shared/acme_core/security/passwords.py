"""Password hashing.

Calls bcrypt directly. passlib 1.7.4 -- its last release, from 2020 -- reads
`bcrypt.__about__.__version__`, which bcrypt 4.1 removed, so every hash emits a
traceback inside a warning. The wrapper it provides is a dozen lines we can own.
"""

from __future__ import annotations

import bcrypt

from acme_core.exceptions import ValidationFailed

# bcrypt truncates silently at 72 BYTES, not characters. A 30-character password
# of emoji or CJK exceeds it, so length must be measured after encoding.
MAX_PASSWORD_BYTES = 72
MIN_PASSWORD_LENGTH = 12

# Cost factor. 12 is ~0.3s on this hardware: slow enough to matter against an
# offline crack, fast enough for a 128 MB Lambda under its request deadline.
_ROUNDS = 12

# Compared against on the user-not-found path so that a failed login takes the
# same time whether or not the account exists. Without it, skipping bcrypt is a
# ~300ms signal that an email is registered.
_DUMMY_HASH = bcrypt.hashpw(b"not-a-real-password", bcrypt.gensalt(rounds=_ROUNDS))


def validate_password_strength(password: str) -> None:
    """Reject a password that is too short or too long to hash safely.

    Length is the only rule. Composition requirements push people toward
    `Password1!`, which is weaker than a long passphrase.

    Args:
        password: The candidate.

    Raises:
        ValidationFailed: The password is unusable.
    """
    encoded = password.encode("utf-8")
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValidationFailed(
            f"Password must be at least {MIN_PASSWORD_LENGTH} characters.",
            details=[
                {
                    "field": "password",
                    "message": f"Must be at least {MIN_PASSWORD_LENGTH} characters.",
                }
            ],
        )
    if len(encoded) > MAX_PASSWORD_BYTES:
        # Rejected, never truncated. Truncating would make "A"*72 + anything
        # authenticate identically, so a user with a long passphrase would have
        # far less protection than they believe, and changing to a longer one
        # would silently be a no-op.
        raise ValidationFailed(
            f"Password must be at most {MAX_PASSWORD_BYTES} bytes.",
            details=[
                {
                    "field": "password",
                    "message": f"Too long: {len(encoded)} bytes, limit {MAX_PASSWORD_BYTES}.",
                }
            ],
        )


def hash_password(password: str) -> str:
    """Hash a password for storage.

    Args:
        password: The plaintext.

    Returns:
        The bcrypt hash, safe to store.

    Raises:
        ValidationFailed: The password does not meet the length rules.
    """
    validate_password_strength(password)
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=_ROUNDS)).decode()


def verify_password(password: str, password_hash: str | None) -> bool:
    """Check a password against a stored hash in constant time.

    Passing `None` -- the user-not-found case -- still performs a full bcrypt
    comparison against a dummy hash, so timing does not disclose whether an
    account exists.

    Args:
        password: The plaintext supplied by the caller.
        password_hash: The stored hash, or None when there is no such user.

    Returns:
        True only when the password matches a real stored hash.
    """
    candidate = password.encode("utf-8")[:MAX_PASSWORD_BYTES]
    if password_hash is None:
        bcrypt.checkpw(candidate, _DUMMY_HASH)
        return False
    try:
        return bcrypt.checkpw(candidate, password_hash.encode("utf-8"))
    except ValueError:
        # A corrupt or truncated hash in the database is not a crash; it is a
        # failed login that gets logged.
        return False
