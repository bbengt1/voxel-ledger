"""Inventory locations endpoints (Phase 3.1).

Thin layer over ``app.services.inventory_locations``. Routers commit the
transaction, map service-layer errors to HTTP, and gate each route on
role.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_role
from app.core.db import get_session
from app.models.auth import User
from app.models.inventory_location import InventoryLocation
from app.schemas.inventory_locations import (
    InventoryLocationCreateRequest,
    InventoryLocationKindLiteral,
    InventoryLocationListResponse,
    InventoryLocationResponse,
    InventoryLocationUpdateRequest,
)
from app.services import inventory_locations as locations_service

router = APIRouter(prefix="/inventory/locations", tags=["inventory-locations"])


async def _refresh_for_response(session: AsyncSession, location: InventoryLocation) -> None:
    await session.refresh(location, ["created_at", "updated_at"])


def _to_response(location: InventoryLocation) -> InventoryLocationResponse:
    return InventoryLocationResponse(
        id=location.id,
        name=location.name,
        code=location.code,
        kind=location.kind.value,  # type: ignore[arg-type]
        description=location.description,
        is_archived=location.is_archived,
        created_at=location.created_at,
        updated_at=location.updated_at,
    )


@router.post(
    "",
    response_model=InventoryLocationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_location(
    payload: InventoryLocationCreateRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role("owner", "production"))],
) -> InventoryLocationResponse:
    try:
        location = await locations_service.create(
            session,
            name=payload.name,
            code=payload.code,
            kind=payload.kind,
            description=payload.description,
            actor_user_id=actor.id,
        )
    except locations_service.DuplicateInventoryLocationError as exc:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from None
    except locations_service.InventoryLocationsServiceError as exc:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from None
    await _refresh_for_response(session, location)
    await session.commit()
    return _to_response(location)


@router.get("", response_model=InventoryLocationListResponse)
async def list_locations(
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(get_current_user)],
    search: Annotated[str | None, Query()] = None,
    kind: Annotated[InventoryLocationKindLiteral | None, Query()] = None,
    is_archived: Annotated[bool | None, Query()] = None,
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> InventoryLocationListResponse:
    try:
        page = await locations_service.list_locations(
            session,
            search=search,
            kind=kind,
            is_archived=is_archived,
            cursor=cursor,
            limit=limit,
        )
    except locations_service.InventoryLocationsServiceError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from None
    return InventoryLocationListResponse(
        items=[_to_response(loc) for loc in page.items],
        next_cursor=page.next_cursor,
    )


@router.get("/{location_id}", response_model=InventoryLocationResponse)
async def get_location(
    location_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(get_current_user)],
) -> InventoryLocationResponse:
    try:
        location = await locations_service.get(session, location_id)
    except locations_service.InventoryLocationNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="inventory location not found"
        ) from None
    return _to_response(location)


@router.patch("/{location_id}", response_model=InventoryLocationResponse)
async def update_location(
    location_id: uuid.UUID,
    payload: InventoryLocationUpdateRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role("owner", "production"))],
) -> InventoryLocationResponse:
    patch = payload.model_dump(exclude_unset=True)
    try:
        location = await locations_service.update(
            session,
            location_id=location_id,
            patch=patch,
            actor_user_id=actor.id,
        )
    except locations_service.InventoryLocationNotFoundError:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="inventory location not found"
        ) from None
    except locations_service.DuplicateInventoryLocationError as exc:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from None
    except locations_service.InventoryLocationsServiceError as exc:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from None
    await _refresh_for_response(session, location)
    await session.commit()
    return _to_response(location)


@router.post("/{location_id}/archive", response_model=InventoryLocationResponse)
async def archive_location(
    location_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role("owner"))],
) -> InventoryLocationResponse:
    try:
        location = await locations_service.archive(
            session, location_id=location_id, actor_user_id=actor.id
        )
    except locations_service.InventoryLocationNotFoundError:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="inventory location not found"
        ) from None
    await _refresh_for_response(session, location)
    await session.commit()
    return _to_response(location)


@router.post("/{location_id}/unarchive", response_model=InventoryLocationResponse)
async def unarchive_location(
    location_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role("owner"))],
) -> InventoryLocationResponse:
    try:
        location = await locations_service.unarchive(
            session, location_id=location_id, actor_user_id=actor.id
        )
    except locations_service.InventoryLocationNotFoundError:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="inventory location not found"
        ) from None
    except locations_service.DuplicateInventoryLocationError as exc:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from None
    await _refresh_for_response(session, location)
    await session.commit()
    return _to_response(location)
