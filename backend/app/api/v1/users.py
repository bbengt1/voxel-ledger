"""Users-admin endpoints (Phase 1.6).

Thin layer over ``app.services.users``. The service owns guard checks
and event emission; the router maps service-layer errors to HTTP and
commits the transaction.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_role
from app.core.db import get_session
from app.models.auth import Role, User
from app.schemas.users import (
    PasswordResetResponse,
    UserCreateRequest,
    UserCreateResponse,
    UserListResponse,
    UserResponse,
    UserUpdateRequest,
)
from app.services import users as users_service

router = APIRouter(prefix="/users", tags=["users"])


async def _refresh_for_response(session: AsyncSession, user: User) -> User:
    """Force-refresh the columns we surface so server-side defaults /
    onupdate triggers are visible. SQLAlchemy doesn't know the new
    ``updated_at`` after a flush — it has to ask the DB.
    """
    await session.refresh(user, ["created_at", "updated_at"])
    return user


def _to_response(user: User, last_login=None) -> UserResponse:
    # Build from the in-memory attributes directly. Pydantic's
    # ``from_attributes=True`` path triggers SQLAlchemy's lazy refresh on
    # commit-expired columns, which fails on the async session. Snapshot
    # what we need synchronously instead.
    return UserResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        is_active=user.is_active,
        created_at=user.created_at,
        updated_at=user.updated_at,
        last_login=last_login,
    )


@router.post("", response_model=UserCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    payload: UserCreateRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role("owner"))],
) -> UserCreateResponse:
    try:
        created = await users_service.create_user(
            session,
            actor=actor,
            email=payload.email,
            full_name=payload.full_name,
            role=payload.role,
        )
    except users_service.DuplicateEmailError as exc:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from None
    await _refresh_for_response(session, created.user)
    await session.commit()
    return UserCreateResponse(
        user=_to_response(created.user),
        generated_password=created.generated_password,
    )


@router.get("", response_model=UserListResponse)
async def list_users(
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(require_role("owner", "bookkeeper"))],
    search: Annotated[str | None, Query()] = None,
    role: Annotated[Role | None, Query()] = None,
    is_active: Annotated[bool | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    cursor: Annotated[str | None, Query()] = None,
) -> UserListResponse:
    try:
        page = await users_service.list_users(
            session,
            search=search,
            role=role,
            is_active=is_active,
            limit=limit,
            cursor=cursor,
        )
    except users_service.UsersServiceError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from None
    return UserListResponse(
        items=[_to_response(u) for u in page.items],
        next_cursor=page.next_cursor,
    )


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(require_role("owner", "bookkeeper"))],
) -> UserResponse:
    try:
        user = await users_service.get_user(session, user_id)
    except users_service.UserNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="user not found"
        ) from None
    last_login = await users_service.get_last_login(session, user_id)
    return _to_response(user, last_login=last_login)


@router.patch("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: uuid.UUID,
    payload: UserUpdateRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role("owner"))],
) -> UserResponse:
    try:
        user = await users_service.update_user(
            session,
            actor=actor,
            user_id=user_id,
            full_name=payload.full_name,
            role=payload.role,
            is_active=payload.is_active,
        )
    except users_service.UserNotFoundError:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="user not found"
        ) from None
    except (
        users_service.SelfDeactivationError,
        users_service.SelfDemotionError,
        users_service.LastOwnerLockoutError,
    ) as exc:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from None
    await _refresh_for_response(session, user)
    await session.commit()
    return _to_response(user)


@router.post("/{user_id}/deactivate", response_model=UserResponse)
async def deactivate_user(
    user_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role("owner"))],
) -> UserResponse:
    try:
        user = await users_service.deactivate_user(session, actor=actor, user_id=user_id)
    except users_service.UserNotFoundError:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="user not found"
        ) from None
    except (
        users_service.SelfDeactivationError,
        users_service.LastOwnerLockoutError,
    ) as exc:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from None
    await _refresh_for_response(session, user)
    await session.commit()
    return _to_response(user)


@router.post("/{user_id}/reactivate", response_model=UserResponse)
async def reactivate_user(
    user_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role("owner"))],
) -> UserResponse:
    try:
        user = await users_service.reactivate_user(session, actor=actor, user_id=user_id)
    except users_service.UserNotFoundError:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="user not found"
        ) from None
    await _refresh_for_response(session, user)
    await session.commit()
    return _to_response(user)


@router.post("/{user_id}/reset-password", response_model=PasswordResetResponse)
async def reset_password(
    user_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role("owner"))],
) -> PasswordResetResponse:
    try:
        result = await users_service.reset_password(session, actor=actor, user_id=user_id)
    except users_service.UserNotFoundError:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="user not found"
        ) from None
    await session.commit()
    return PasswordResetResponse(
        user_id=result.user_id,
        generated_password=result.generated_password,
    )
