"""Inventory on-hand query endpoint (Phase 3.3, #52).

Thin layer over ``inventory_on_hand`` projection state. All
authenticated roles can read these — production needs to plan
restocks, sales needs to know what's sellable, owner runs the show.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.db import get_session
from app.models.auth import User
from app.models.inventory_on_hand import InventoryOnHand
from app.schemas.inventory_on_hand import (
    EntityKindLiteral,
    OnHandListResponse,
    OnHandRowResponse,
    OnHandSummaryResponse,
)

router = APIRouter(prefix="/inventory/on-hand", tags=["inventory-on-hand"])


@router.get("", response_model=OnHandListResponse)
async def list_on_hand(
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(get_current_user)],
    entity_kind: Annotated[EntityKindLiteral | None, Query()] = None,
    entity_id: Annotated[uuid.UUID | None, Query()] = None,
    location_id: Annotated[uuid.UUID | None, Query()] = None,
) -> OnHandListResponse:
    """Return ``inventory_on_hand`` rows, optionally filtered.

    Default shape: a list of per-(entity, location) rows AND a list of
    per-entity summaries (total + per-location map). The caller can use
    either depending on whether they need the breakdown or the rollup.
    """
    stmt = select(InventoryOnHand)
    if entity_kind is not None:
        stmt = stmt.where(InventoryOnHand.entity_kind == entity_kind)
    if entity_id is not None:
        stmt = stmt.where(InventoryOnHand.entity_id == entity_id)
    if location_id is not None:
        stmt = stmt.where(InventoryOnHand.location_id == location_id)
    rows = list((await session.execute(stmt)).scalars().all())

    detail_rows = [
        OnHandRowResponse(
            entity_kind=r.entity_kind,
            entity_id=r.entity_id,
            location_id=r.location_id,
            on_hand=r.on_hand,
        )
        for r in rows
    ]

    grouped: dict[tuple[str, uuid.UUID], dict[uuid.UUID, Decimal]] = defaultdict(dict)
    for r in rows:
        grouped[(r.entity_kind, r.entity_id)][r.location_id] = Decimal(str(r.on_hand))
    summaries = [
        OnHandSummaryResponse(
            entity_kind=kind,
            entity_id=eid,
            total_on_hand=sum(per_loc.values(), start=Decimal("0")),
            per_location=per_loc,
        )
        for (kind, eid), per_loc in grouped.items()
    ]
    return OnHandListResponse(rows=detail_rows, summaries=summaries)
