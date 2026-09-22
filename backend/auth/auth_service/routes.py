"""HTTP routes for the auth service, mounted under /api/auth.

Every handler is a plain `def`: SQLAlchemy is synchronous, and a sync call
inside `async def` would block the event loop for every other request (A6).
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, Response, status

from acme_core.dependencies import AdminPrincipal, CurrentUser, DbSession
from acme_core.errors import error_responses
from acme_core.models.enums import Role
from acme_core.models.user import User
from acme_core.schemas.auth import (
    AdminCreateUserRequest,
    AdminUpdateUserRequest,
    ChangePasswordRequest,
    EngineerProfileOut,
    LoginRequest,
    MeOut,
    RefreshRequest,
    RegisterAccepted,
    RegisterRequest,
    TokenPair,
    UserFilters,
    UserOut,
)
from acme_core.schemas.common import Page
from auth_service import service

router = APIRouter()


def _token_pair(issued: service.IssuedTokens) -> TokenPair:
    return TokenPair(
        access_token=issued.access_token,
        refresh_token=issued.refresh_token,
        expires_in=issued.expires_in,
    )


def _me(user: User) -> MeOut:
    """Build the /me body. A profile left behind by a demotion is not shown."""
    profile = user.engineer_profile if user.role is Role.ENGINEER else None
    return MeOut(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        occupation=user.occupation,
        date_of_birth=user.date_of_birth,
        is_active=user.is_active,
        created_at=user.created_at,
        engineer_profile=EngineerProfileOut.model_validate(profile) if profile else None,
    )


# --------------------------------------------------------------------------- public


@router.post(
    "/register",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=RegisterAccepted,
    responses=error_responses(400),
    tags=["session"],
    summary="Register as an Employee",
)
def register(body: RegisterRequest, session: DbSession) -> RegisterAccepted:
    """Self-register with an @acme.inc address.

    The response is identical whether or not the address was already
    registered, so this endpoint cannot be used to discover accounts.
    """
    service.register(session, body)
    return RegisterAccepted(message=service.REGISTER_ACCEPTED)


@router.post(
    "/login",
    response_model=TokenPair,
    responses=error_responses(400, 401),
    tags=["session"],
    summary="Sign in",
)
def login(body: LoginRequest, session: DbSession) -> TokenPair:
    """Exchange credentials for an access token and a refresh token."""
    return _token_pair(service.login(session, body))


@router.post(
    "/refresh",
    response_model=TokenPair,
    responses=error_responses(400, 401),
    tags=["session"],
    summary="Rotate a refresh token",
)
def refresh(body: RefreshRequest, session: DbSession) -> TokenPair:
    """Exchange a refresh token for a new pair. The presented token is retired.

    Presenting an already-retired token revokes every session descended from
    the same sign-in and returns `refresh_token_reused`.
    """
    return _token_pair(service.refresh(session, body.refresh_token))


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=error_responses(400),
    tags=["session"],
    summary="Sign out this device",
)
def logout(body: RefreshRequest, session: DbSession) -> Response:
    """Revoke this device's refresh token. Needs no access token, and always 204."""
    service.logout(session, body.refresh_token)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --------------------------------------------------------------------------- the caller


@router.post(
    "/logout-all",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=error_responses(401),
    tags=["session"],
    summary="Sign out everywhere",
)
def logout_all(user: CurrentUser, session: DbSession) -> Response:
    """End every session on every device, including this one."""
    service.logout_all(session, user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/me", response_model=MeOut, responses=error_responses(401), tags=["me"], summary="Who am I"
)
def me(user: CurrentUser) -> MeOut:
    """Return the caller, including their engineer profile if they are an Engineer."""
    return _me(user)


@router.post(
    "/me/password",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=error_responses(400, 401),
    tags=["me"],
    summary="Change my password",
)
def change_password(body: ChangePasswordRequest, user: CurrentUser, session: DbSession) -> Response:
    """Change the caller's password. Every session ends; sign in again afterwards."""
    service.change_password(session, user, body)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --------------------------------------------------------------------------- admin


@router.get(
    "/users",
    response_model=Page[UserOut],
    responses=error_responses(400, 401, 403),
    tags=["users"],
    summary="List users",
)
def list_users(
    _admin: AdminPrincipal,
    session: DbSession,
    filters: Annotated[UserFilters, Query()],
) -> Page[UserOut]:
    """Page through every user. Filter by role, activity, or a name/email search."""
    rows, total = service.list_users(session, filters)
    return Page[UserOut](
        items=[UserOut.model_validate(u) for u in rows],
        total=total,
        limit=filters.limit,
        offset=filters.offset,
    )


@router.post(
    "/users",
    status_code=status.HTTP_201_CREATED,
    response_model=UserOut,
    responses=error_responses(400, 401, 403, 409),
    tags=["users"],
    summary="Create a user",
)
def create_user(
    body: AdminCreateUserRequest,
    _admin: AdminPrincipal,
    session: DbSession,
    response: Response,
) -> UserOut:
    """Create a user with any role. An Engineer requires a specialty."""
    user = service.create_user(session, body)
    response.headers["Location"] = f"/api/auth/users/{user.id}"
    return UserOut.model_validate(user)


@router.get(
    "/users/{user_id}",
    response_model=UserOut,
    responses=error_responses(400, 401, 403, 404),
    tags=["users"],
    summary="Get a user",
)
def get_user(user_id: uuid.UUID, _admin: AdminPrincipal, session: DbSession) -> UserOut:
    """Fetch one user."""
    return UserOut.model_validate(service.get_user(session, user_id))


@router.put(
    "/users/{user_id}",
    response_model=UserOut,
    responses=error_responses(400, 401, 403, 404, 409),
    tags=["users"],
    summary="Update a user",
)
def update_user(
    user_id: uuid.UUID,
    body: AdminUpdateUserRequest,
    admin: AdminPrincipal,
    session: DbSession,
) -> UserOut:
    """Change a user's name, role or activity. Omitted fields are unchanged.

    A role change or deactivation ends the user's sessions immediately.
    """
    return UserOut.model_validate(service.update_user(session, admin, user_id, body))


@router.delete(
    "/users/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=error_responses(400, 401, 403, 404, 409),
    tags=["users"],
    summary="Deactivate a user",
)
def delete_user(user_id: uuid.UUID, admin: AdminPrincipal, session: DbSession) -> Response:
    """Soft-delete: the user can no longer sign in, and their history is kept."""
    service.deactivate_user(session, admin, user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
