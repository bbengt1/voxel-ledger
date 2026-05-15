"""Divisions endpoints (Phase 4.5, #68).

Thin layer over ``app.services.divisions``. Routers commit the
transaction, map service-layer errors to HTTP, and gate each route on
role.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_role
from app.core.db import get_session
from app.models.auth import User
from app.models.division import Division
from app.schemas.divisions import (
    DivisionCreateRequest,
    DivisionListResponse,
    DivisionResponse,
    DivisionUpdateRequest,
)
from app.services import divisions as divisions_service

router = APIRouter(prefix="/accounting/divisions", tags=["divisions"])


async def _refresh(session: AsyncSession, division: Division) -> None:
    await session.refresh(division, ["created_at", "updated_at"])


def _to_response(division: Division) -> DivisionResponse:
    return DivisionResponse(
        id=division.id,
        name=division.name,
        code=division.code,
        is_archived=division.is_archived,
        created_at=division.created_at,
        updated_at=division.updated_at,
    )


def _map_error(exc: divisions_service.DivisionsServiceError) -> HTTPException:
    if isinstance(exc, divisions_service.DivisionNotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="division not found")
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.post(
    "",
    response_model=DivisionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_division(
    payload: DivisionCreateRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role("owner"))],
) -> DivisionResponse:
    try:
        division = await divisions_service.create(
            session,
            name=payload.name,
            code=payload.code,
            actor_user_id=actor.id,
        )
    except divisions_service.DivisionsServiceError as exc:
        await session.rollback()
        raise _map_error(exc) from None
    await _refresh(session, division)
    await session.commit()
    return _to_response(division)


@router.get("", response_model=DivisionListResponse)
async def list_divisions(
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(require_role("owner", "bookkeeper"))],
    search: Annotated[str | None, Query()] = None,
    is_archived: Annotated[bool | None, Query()] = None,
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> DivisionListResponse:
    try:
        page = await divisions_service.list_divisions(
            session,
            search=search,
            is_archived=is_archived,
            cursor=cursor,
            limit=limit,
        )
    except divisions_service.DivisionsServiceError as exc:
        raise _map_error(exc) from None
    return DivisionListResponse(
        items=[_to_response(d) for d in page.items],
        next_cursor=page.next_cursor,
    )


@router.get("/{division_id}", response_model=DivisionResponse)
async def get_division(
    division_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(require_role("owner", "bookkeeper"))],
) -> DivisionResponse:
    try:
        division = await divisions_service.get(session, division_id)
    except divisions_service.DivisionsServiceError as exc:
        raise _map_error(exc) from None
    return _to_response(division)


@router.patch("/{division_id}", response_model=DivisionResponse)
async def update_division(
    division_id: uuid.UUID,
    payload: DivisionUpdateRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role("owner"))],
) -> DivisionResponse:
    patch = payload.model_dump(exclude_unset=True)
    try:
        division = await divisions_service.update(
            session,
            division_id=division_id,
            patch=patch,
            actor_user_id=actor.id,
        )
    except divisions_service.DivisionsServiceError as exc:
        await session.rollback()
        raise _map_error(exc) from None
    await _refresh(session, division)
    await session.commit()
    return _to_response(division)


@router.post("/{division_id}/archive", response_model=DivisionResponse)
async def archive_division(
    division_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role("owner"))],
) -> DivisionResponse:
    try:
        division = await divisions_service.archive(
            session, division_id=division_id, actor_user_id=actor.id
        )
    except divisions_service.DivisionsServiceError as exc:
        await session.rollback()
        raise _map_error(exc) from None
    await _refresh(session, division)
    await session.commit()
    return _to_response(division)


@router.post("/{division_id}/unarchive", response_model=DivisionResponse)
async def unarchive_division(
    division_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role("owner"))],
) -> DivisionResponse:
    try:
        division = await divisions_service.unarchive(
            session, division_id=division_id, actor_user_id=actor.id
        )
    except divisions_service.DivisionsServiceError as exc:
        await session.rollback()
        raise _map_error(exc) from None
    await _refresh(session, division)
    await session.commit()
    return _to_response(division)
