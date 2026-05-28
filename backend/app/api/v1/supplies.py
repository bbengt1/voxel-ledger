"""Supplies endpoints (Phase 2.2).

Thin layer over ``app.services.supplies``. Routers commit the
transaction, map service-layer errors to HTTP, and gate each route on
role.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_role
from app.core.db import get_session
from app.models.auth import User
from app.models.supply import Supply
from app.schemas.supplies import (
    SupplyCreateRequest,
    SupplyListResponse,
    SupplyResponse,
    SupplyUpdateRequest,
)
from app.services import custom_fields as cf_service
from app.services import inventory_alerts as alerts_service
from app.services import supplies as supplies_service

router = APIRouter(prefix="/supplies", tags=["supplies"])


async def _refresh_for_response(session: AsyncSession, supply: Supply) -> None:
    await session.refresh(supply, ["created_at", "updated_at"])


async def _to_response(session: AsyncSession, supply: Supply) -> SupplyResponse:
    per_location = await alerts_service.on_hand_for_entity(
        session=session, entity_kind="supply", entity_id=supply.id
    )
    total = sum(per_location.values(), start=Decimal("0"))
    return SupplyResponse(
        id=supply.id,
        name=supply.name,
        unit=supply.unit,
        unit_cost=supply.unit_cost,
        vendor=supply.vendor,
        item_number=supply.item_number,
        place_of_purchase=supply.place_of_purchase,
        pieces_per_unit=supply.pieces_per_unit,
        total_on_hand=total,
        per_location_on_hand=per_location,
        low_stock_threshold=supply.low_stock_threshold,
        is_archived=supply.is_archived,
        custom_fields=dict(supply.custom_fields or {}),
        created_at=supply.created_at,
        updated_at=supply.updated_at,
    )


@router.post(
    "",
    response_model=SupplyResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_supply(
    payload: SupplyCreateRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role("owner", "production"))],
) -> SupplyResponse:
    try:
        supply = await supplies_service.create(
            session,
            name=payload.name,
            unit=payload.unit,
            unit_cost=payload.unit_cost,
            vendor=payload.vendor,
            item_number=payload.item_number,
            place_of_purchase=payload.place_of_purchase,
            pieces_per_unit=payload.pieces_per_unit,
            low_stock_threshold=payload.low_stock_threshold,
            actor_user_id=actor.id,
            custom_fields=payload.custom_fields,
        )
    except supplies_service.DuplicateSupplyError as exc:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from None
    except cf_service.CustomFieldValidationError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"message": "custom_fields validation failed", "errors": exc.errors},
        ) from None
    await _refresh_for_response(session, supply)
    await session.commit()
    return await _to_response(session, supply)


@router.get("", response_model=SupplyListResponse)
async def list_supplies(
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(get_current_user)],
    search: Annotated[str | None, Query()] = None,
    is_archived: Annotated[bool | None, Query()] = None,
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> SupplyListResponse:
    try:
        page = await supplies_service.list_supplies(
            session,
            search=search,
            is_archived=is_archived,
            cursor=cursor,
            limit=limit,
        )
    except supplies_service.SuppliesServiceError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from None
    return SupplyListResponse(
        items=[await _to_response(session, s) for s in page.items],
        next_cursor=page.next_cursor,
    )


@router.get("/{supply_id}", response_model=SupplyResponse)
async def get_supply(
    supply_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(get_current_user)],
) -> SupplyResponse:
    try:
        supply = await supplies_service.get(session, supply_id)
    except supplies_service.SupplyNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="supply not found"
        ) from None
    return await _to_response(session, supply)


@router.patch("/{supply_id}", response_model=SupplyResponse)
async def update_supply(
    supply_id: uuid.UUID,
    payload: SupplyUpdateRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role("owner", "production"))],
) -> SupplyResponse:
    patch = payload.model_dump(exclude_unset=True)
    custom_fields = patch.pop("custom_fields", None)
    try:
        supply = await supplies_service.update(
            session,
            supply_id=supply_id,
            patch=patch,
            actor_user_id=actor.id,
            custom_fields=custom_fields,
        )
    except supplies_service.SupplyNotFoundError:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="supply not found"
        ) from None
    except supplies_service.DuplicateSupplyError as exc:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from None
    except cf_service.CustomFieldValidationError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"message": "custom_fields validation failed", "errors": exc.errors},
        ) from None
    await _refresh_for_response(session, supply)
    await session.commit()
    return await _to_response(session, supply)


@router.post("/{supply_id}/archive", response_model=SupplyResponse)
async def archive_supply(
    supply_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role("owner"))],
) -> SupplyResponse:
    try:
        supply = await supplies_service.archive(
            session, supply_id=supply_id, actor_user_id=actor.id
        )
    except supplies_service.SupplyNotFoundError:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="supply not found"
        ) from None
    await _refresh_for_response(session, supply)
    await session.commit()
    return await _to_response(session, supply)


@router.post("/{supply_id}/unarchive", response_model=SupplyResponse)
async def unarchive_supply(
    supply_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role("owner"))],
) -> SupplyResponse:
    try:
        supply = await supplies_service.unarchive(
            session, supply_id=supply_id, actor_user_id=actor.id
        )
    except supplies_service.SupplyNotFoundError:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="supply not found"
        ) from None
    except supplies_service.DuplicateSupplyError as exc:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from None
    await _refresh_for_response(session, supply)
    await session.commit()
    return await _to_response(session, supply)
