"""Low-stock alerts endpoint (Phase 3.3, #52)."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.db import get_session
from app.models.auth import User
from app.schemas.inventory_on_hand import (
    EntityKindLiteral,
    LowStockAlertListResponse,
    LowStockAlertResponse,
)
from app.services import inventory_alerts as alerts_service

router = APIRouter(prefix="/inventory/alerts", tags=["inventory-alerts"])


@router.get("/low-stock", response_model=LowStockAlertListResponse)
async def list_low_stock_alerts(
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(get_current_user)],
    entity_kind: Annotated[EntityKindLiteral | None, Query()] = None,
    location_id: Annotated[uuid.UUID | None, Query()] = None,
) -> LowStockAlertListResponse:
    """Return entities whose ``total_on_hand < low_stock_threshold``.

    Entities with no configured threshold never appear. Sorted by
    deficit descending. All authenticated roles can read this — the
    alert surface needs broad visibility.
    """
    alerts = await alerts_service.list_low_stock(
        session=session, entity_kind=entity_kind, location_id=location_id
    )
    return LowStockAlertListResponse(
        items=[
            LowStockAlertResponse(
                entity_kind=a.entity_kind,
                entity_id=a.entity_id,
                entity_name=a.entity_name,
                threshold=a.threshold,
                total_on_hand=a.total_on_hand,
                deficit=a.deficit,
            )
            for a in alerts
        ]
    )
