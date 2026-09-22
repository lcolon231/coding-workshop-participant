"""Authentication and user-administration rules.

Routes stay thin: they parse, call one function here, and shape the response.
Everything that decides -- who may sign in, when a session dies, which user
edits are allowed -- is in this module, where it can be read in one place.
"""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass
from typing import Final

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from acme_core.exceptions import (
    Conflict,
    NotFound,
    RefreshTokenReused,
    TokenExpired,
    Unauthenticated,
    ValidationFailed,
)
from acme_core.logging_config import get_logger
from acme_core.models.enums import Role
from acme_core.models.user import EngineerProfile, RefreshToken, User
from acme_core.schemas.auth import (
    AdminCreateUserRequest,
    AdminUpdateUserRequest,
    ChangePasswordRequest,
    LoginRequest,
    RegisterRequest,
    UserFilters,
)
from acme_core.security.passwords import hash_password, verify_password
from acme_core.security.principal import Principal, ensure_session_not_revoked
from acme_core.security.secret import get_jwt_secret
from acme_core.security.tokens import (
    TokenType,
    decode_token,
    hash_refresh_token,
    issue_token,
)
from auth_service import repository as repo

_logger = get_logger(__name__)

# Account-based lockout (S8). Never IP-based: on the Function URL the caller
# controls X-Forwarded-For, and through CloudFront every request comes from an
# edge node, so an IP counter is bypassable by construction.
MAX_FAILED_LOGINS: Final[int] = 5
LOCKOUT: Final[dt.timedelta] = dt.timedelta(minutes=15)

# One message for every sign-in failure. Distinguishing "no such user",
# "wrong password", "deactivated" and "locked" would turn the login form into
# an account-enumeration oracle.
LOGIN_FAILED: Final[str] = "Invalid email or password, or the account is temporarily locked."

REGISTER_ACCEPTED: Final[str] = (
    "If this address can be registered, the account is ready. Sign in to continue."
)


@dataclass(frozen=True, slots=True)
class IssuedTokens:
    """A freshly minted access/refresh pair."""

    access_token: str
    refresh_token: str
    expires_in: int


def _now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def _aware(value: dt.datetime) -> dt.datetime:
    """Treat a naive timestamp from the database as UTC."""
    return value if value.tzinfo is not None else value.replace(tzinfo=dt.UTC)


# --------------------------------------------------------------------------- sessions


def revoke_all_sessions(session: Session, user: User) -> None:
    """Kill every access and refresh token the user holds.

    `sessions_valid_from` is compared against a token's integer `iat`, so it is
    set to the *next* whole second: every token issued up to and including this
    one dies, and `_issue_pair` stamps new tokens no earlier than the cutoff so
    a sign-in in the same second still works.

    Args:
        session: The request's session.
        user: The user whose sessions end.
    """
    now = _now()
    user.sessions_valid_from = now.replace(microsecond=0) + dt.timedelta(seconds=1)
    repo.revoke(repo.live_tokens_for_user(session, user.id), now)


def _issue_pair(
    session: Session, user: User, family_id: uuid.UUID | None = None
) -> IssuedTokens:
    """Mint an access and a refresh token and persist the refresh token's hash.

    Args:
        session: The request's session.
        user: Who the tokens identify.
        family_id: Continue a rotation family; omit to start a new one (login).

    Returns:
        The encoded tokens.
    """
    secret = get_jwt_secret(session)
    # Never stamp a token before the user's session cutoff, or a sign-in in the
    # same second as a logout-all would be born revoked.
    issued = max(_now(), _aware(user.sessions_valid_from))
    access, access_claims = issue_token(user.id, TokenType.ACCESS, secret, now=issued)
    refresh, refresh_claims = issue_token(user.id, TokenType.REFRESH, secret, now=issued)
    session.add(
        RefreshToken(
            user_id=user.id,
            token_hash=hash_refresh_token(refresh),
            family_id=family_id or uuid.uuid4(),
            issued_at=refresh_claims.issued_at,
            expires_at=refresh_claims.expires_at,
        )
    )
    session.flush()
    lifetime = int((access_claims.expires_at - access_claims.issued_at).total_seconds())
    return IssuedTokens(access_token=access, refresh_token=refresh, expires_in=lifetime)


# --------------------------------------------------------------------------- public auth


def register(session: Session, request: RegisterRequest) -> None:
    """Create an Employee account, or do nothing if the email is taken.

    Both paths look identical from outside: same response, and the taken path
    still pays for a bcrypt hash so the timing matches too (S8).

    Args:
        session: The request's session.
        request: The validated registration.
    """
    password_hash = hash_password(request.password)
    if repo.get_user_by_email(session, request.email) is not None:
        _logger.info("register_existing_email")
        return
    try:
        # A savepoint, so losing a race to a concurrent registration of the
        # same address rolls back only this insert, not the whole request.
        with session.begin_nested():
            session.add(
                User(
                    email=request.email,
                    full_name=request.full_name,
                    password_hash=password_hash,
                    role=Role.EMPLOYEE,
                )
            )
    except IntegrityError:
        _logger.info("register_lost_race")
        return
    _logger.info("register_created")


def login(session: Session, request: LoginRequest) -> IssuedTokens:
    """Verify credentials and start a new session.

    Args:
        session: The request's session.
        request: The credentials.

    Returns:
        A new token pair in a new rotation family.

    Raises:
        Unauthenticated: For every failure, with one message.
    """
    user = repo.get_user_by_email(session, request.email)
    # Always run bcrypt -- against a dummy hash when there is no user -- so the
    # response time does not reveal whether the address is registered.
    password_ok = verify_password(request.password, user.password_hash if user else None)
    if user is None:
        raise Unauthenticated(LOGIN_FAILED)

    now = _now()
    locked = user.locked_until is not None and _aware(user.locked_until) > now
    if locked or not user.is_active:
        raise Unauthenticated(LOGIN_FAILED)

    if not password_ok:
        user.failed_login_count += 1
        if user.failed_login_count >= MAX_FAILED_LOGINS:
            user.locked_until = now + LOCKOUT
            user.failed_login_count = 0
            _logger.warning("login_account_locked", extra={"user_id": str(user.id)})
        # Committed before raising: the request's session rolls back on any
        # exception, which would otherwise erase the very counter that makes
        # the lockout work.
        session.commit()
        raise Unauthenticated(LOGIN_FAILED)

    user.failed_login_count = 0
    user.locked_until = None
    return _issue_pair(session, user)


def refresh(session: Session, raw_token: str) -> IssuedTokens:
    """Rotate a refresh token: revoke it and issue a new pair in its family.

    Args:
        session: The request's session.
        raw_token: The presented refresh token.

    Returns:
        A new token pair.

    Raises:
        WrongTokenType: An access token was presented.
        RefreshTokenReused: The token was already rotated; the family is revoked.
        Unauthenticated: The token is invalid, expired, unknown or its user is
            no longer allowed to sign in.
    """
    secret = get_jwt_secret(session)
    try:
        claims = decode_token(raw_token, secret, expected_type=TokenType.REFRESH)
    except TokenExpired as exc:
        # `token_expired` means "refresh your access token" to the client. On
        # the refresh endpoint that advice loops, so say what is true instead.
        raise Unauthenticated("Session has expired; sign in again.") from exc

    stored = repo.get_refresh_token_for_update(session, hash_refresh_token(raw_token))
    if stored is None:
        raise Unauthenticated("Session is not valid; sign in again.")

    now = _now()
    if stored.revoked_at is not None:
        # A revoked token being presented means a copy exists somewhere. Kill
        # the whole family so the thief's rotated descendant dies too.
        repo.revoke(repo.live_tokens_in_family(session, stored.family_id), now)
        session.commit()
        _logger.warning("refresh_token_reused", extra={"user_id": str(stored.user_id)})
        raise RefreshTokenReused()

    user = repo.get_user(session, stored.user_id)
    if user is None or not user.is_active or _aware(stored.expires_at) <= now:
        raise Unauthenticated("Session is not valid; sign in again.")
    ensure_session_not_revoked(user, claims.issued_at)

    stored.revoked_at = now
    return _issue_pair(session, user, family_id=stored.family_id)


def logout(session: Session, raw_token: str) -> None:
    """End one device's session by revoking its refresh-token family.

    Silent for an unknown token: logout must not become an oracle for which
    tokens exist. The token is matched by hash, which only its holder can
    produce, so no signature check is needed to decide what to revoke.

    Args:
        session: The request's session.
        raw_token: The refresh token to retire.
    """
    stored = repo.get_refresh_token_for_update(session, hash_refresh_token(raw_token))
    if stored is not None:
        repo.revoke(repo.live_tokens_in_family(session, stored.family_id), _now())


def logout_all(session: Session, user: User) -> None:
    """End every session the user has, on every device."""
    revoke_all_sessions(session, user)


def change_password(session: Session, user: User, request: ChangePasswordRequest) -> None:
    """Replace the caller's password and end all their sessions.

    Args:
        session: The request's session.
        user: The authenticated caller.
        request: Current and new passwords.

    Raises:
        ValidationFailed: The current password is wrong, or the new one is
            unusable.
    """
    if not verify_password(request.current_password, user.password_hash):
        raise ValidationFailed(
            "Current password is incorrect.",
            details=[{"field": "current_password", "message": "Incorrect password."}],
        )
    user.password_hash = hash_password(request.new_password)
    revoke_all_sessions(session, user)


# --------------------------------------------------------------------------- admin


def list_users(session: Session, filters: UserFilters) -> tuple[list[User], int]:
    """Page through users."""
    return repo.list_users(session, filters)


def get_user(session: Session, user_id: uuid.UUID) -> User:
    """Fetch a user or raise NotFound."""
    user = repo.get_user(session, user_id)
    if user is None:
        raise NotFound("User not found.")
    return user


def create_user(session: Session, request: AdminCreateUserRequest) -> User:
    """Create a user with any role; an Engineer gets a profile in the same transaction.

    Raises:
        Conflict: The email is taken. Admins are trusted, so unlike
            registration this is disclosed.
    """
    if repo.get_user_by_email(session, request.email) is not None:
        raise Conflict("A user with this email already exists.")
    user = User(
        email=request.email,
        full_name=request.full_name,
        password_hash=hash_password(request.password),
        role=request.role,
    )
    if request.role is Role.ENGINEER and request.specialty is not None:
        user.engineer_profile = EngineerProfile(specialty=request.specialty)
    try:
        with session.begin_nested():
            session.add(user)
    except IntegrityError as exc:
        raise Conflict("A user with this email already exists.") from exc
    return user


def _guard_removal(session: Session, actor: Principal, target: User, action: str) -> None:
    """Refuse demotions and deactivations that would strand the system.

    Raises:
        Conflict: The admin is acting on themselves, or the target still holds
            open assignments that nobody could then work.
    """
    if target.id == actor.user_id:
        # Guarantees at least one admin always remains able to undo mistakes.
        raise Conflict(f"You cannot {action} your own account.")
    if target.role is Role.ENGINEER:
        open_count = repo.count_open_assignments(session, target.id)
        if open_count:
            raise Conflict(
                f"This engineer has {open_count} open assignment(s); reassign them first."
            )


def update_user(
    session: Session, actor: Principal, user_id: uuid.UUID, request: AdminUpdateUserRequest
) -> User:
    """Apply an admin's edits to a user.

    Raises:
        NotFound: No such user.
        Conflict: A self-demotion, self-deactivation, or removing an engineer
            who still has open work.
        ValidationFailed: Promoting to Engineer without a specialty, or giving
            a specialty to someone who will not be an Engineer.
    """
    user = repo.get_user_for_update(session, user_id)
    if user is None:
        raise NotFound("User not found.")
    changes = request.changes()

    new_role = changes.get("role", user.role)
    role_changes = new_role is not user.role
    deactivates = changes.get("is_active") is False and user.is_active

    if (role_changes and user.role in (Role.FACILITY_ADMIN, Role.ENGINEER)) or deactivates:
        verb = "deactivate" if deactivates else "change the role of"
        _guard_removal(session, actor, user, verb)

    specialty = changes.get("specialty")
    if new_role is Role.ENGINEER:
        profile = repo.get_engineer_profile(session, user.id)
        if profile is None:
            if specialty is None:
                raise ValidationFailed(
                    "A specialty is required to make this user an Engineer.",
                    details=[{"field": "specialty", "message": "This value is required."}],
                )
            user.engineer_profile = EngineerProfile(specialty=specialty)
        elif specialty is not None:
            profile.specialty = specialty
    elif specialty is not None:
        raise ValidationFailed(
            "A specialty applies only to an Engineer.",
            details=[{"field": "specialty", "message": "Only an Engineer has a specialty."}],
        )

    if "full_name" in changes:
        user.full_name = changes["full_name"]
    if "is_active" in changes:
        user.is_active = changes["is_active"]
    user.role = new_role

    # A demotion or deactivation must bite on the target's very next request,
    # not in up to thirty minutes when their access token expires (S7).
    if role_changes or deactivates:
        revoke_all_sessions(session, user)
    session.flush()
    return user


def deactivate_user(session: Session, actor: Principal, user_id: uuid.UUID) -> None:
    """Soft-delete a user.

    A hard delete would orphan or cascade away the incidents that name them as
    reporter or assignee. Idempotent: deactivating an inactive user succeeds.

    Raises:
        NotFound: No such user.
        Conflict: The admin is deactivating themselves, or an engineer with
            open assignments.
    """
    user = repo.get_user_for_update(session, user_id)
    if user is None:
        raise NotFound("User not found.")
    if not user.is_active:
        return
    _guard_removal(session, actor, user, "deactivate")
    user.is_active = False
    revoke_all_sessions(session, user)
