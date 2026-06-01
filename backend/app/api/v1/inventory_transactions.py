"""Inventory transactions endpoints (Phase 3.2, #51).

Thin layer over ``app.services.inventory_transactions``. The router
commits the transaction, maps service-layer errors to HTTP, and gates
each kind on a role:

* ``sale_out`` — owner / sales.
* every other kind — owner / production.

The list/get endpoints are visible to every authenticated role.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_role
from app.core.db import get_session
from app.models.auth import User
from app.models.inventory_transaction import InventoryTransaction
from app.schemas.inventory_transactions import (
    InventoryEntityKindReadLiteral,
    InventoryTransactionCreate,
    InventoryTransactionKindLiteral,
    InventoryTransactionListResponse,
    InventoryTransactionResponse,
    InventoryTransferCreate,
    InventoryTransferResponse,
)
from app.services import inventory_transactions as transactions_service

router = APIRouter(prefix="/inventory/transactions", tags=["inventory-transactions"])

# Kinds routed through the sales-role gate; everything else needs
# owner-or-production. Adjustments stay with owner/production by design
# — adjusting stock is a production / inventory-keeper task.
_SALES_KINDS: frozenset[str] = frozenset({"sale_out"})


def _to_response(tx: InventoryTransaction) -> InventoryTransactionResponse:
    return InventoryTransactionResponse.model_validate(tx)


def _map_service_error(exc: Exception) -> HTTPException:
    """Map service-level exceptions to FastAPI HTTPExceptions."""
    if isinstance(
        exc,
        transactions_service.EntityNotFoundError | transactions_service.LocationNotFoundError,
    ):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.post(
    "",
    response_model=InventoryTransactionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_transaction(
    payload: InventoryTransactionCreate,
    session: Annotated[AsyncSession, Depends(get_session)],
    # Both role groups can reach this endpoint; per-kind gating happens
    # inside the handler so we can return a structured 403 for a sales
    # user attempting a production kind.
    actor: Annotated[User, Depends(get_current_user)],
) -> InventoryTransactionResponse:
    allowed_for_kind = (
        {"owner", "sales"} if payload.kind in _SALES_KINDS else {"owner", "production"}
    )
    if actor.role.value not in allowed_for_kind:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"role {actor.role.value!r} cannot record {payload.kind} transactions",
        )

    try:
        tx = await transactions_service.record(
            session,
            kind=payload.kind,
            entity_kind=payload.entity_kind,
            entity_id=payload.entity_id,
            location_id=payload.location_id,
            quantity=payload.quantity,
            actor_user_id=actor.id,
            occurred_at=payload.occurred_at,
            reason=payload.reason,
            unit_cost=payload.unit_cost,
            linked_job_id=payload.linked_job_id,
            linked_sale_id=payload.linked_sale_id,
        )
    except transactions_service.InventoryTransactionsServiceError as exc:
        await session.rollback()
        raise _map_service_error(exc) from None
    await session.commit()
    await session.refresh(tx)
    return _to_response(tx)


@router.post(
    "/transfer",
    response_model=InventoryTransferResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_transfer(
    payload: InventoryTransferCreate,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role("owner", "production"))],
) -> InventoryTransferResponse:
    try:
        out_tx, in_tx = await transactions_service.record_transfer(
            session,
            entity_kind=payload.entity_kind,
            entity_id=payload.entity_id,
            from_location_id=payload.from_location_id,
            to_location_id=payload.to_location_id,
            quantity=payload.quantity,
            actor_user_id=actor.id,
            occurred_at=payload.occurred_at,
            reason=payload.reason,
        )
    except transactions_service.InventoryTransactionsServiceError as exc:
        await session.rollback()
        raise _map_service_error(exc) from None
    await session.commit()
    await session.refresh(out_tx)
    await session.refresh(in_tx)
    assert out_tx.transfer_pair_id is not None  # invariant: set by service
    return InventoryTransferResponse(
        transfer_pair_id=out_tx.transfer_pair_id,
        out_transaction=_to_response(out_tx),
        in_transaction=_to_response(in_tx),
    )


@router.get("", response_model=InventoryTransactionListResponse)
async def list_transactions(
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(get_current_user)],
    entity_kind: Annotated[InventoryEntityKindReadLiteral | None, Query()] = None,
    entity_id: Annotated[uuid.UUID | None, Query()] = None,
    location_id: Annotated[uuid.UUID | None, Query()] = None,
    kind: Annotated[InventoryTransactionKindLiteral | None, Query()] = None,
    from_at: Annotated[datetime | None, Query()] = None,
    to_at: Annotated[datetime | None, Query()] = None,
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> InventoryTransactionListResponse:
    try:
        page = await transactions_service.list_transactions(
            session,
            entity_kind=entity_kind,
            entity_id=entity_id,
            location_id=location_id,
            kind=kind,
            from_at=from_at,
            to_at=to_at,
            cursor=cursor,
            limit=limit,
        )
    except transactions_service.InventoryTransactionsServiceError as exc:
        raise _map_service_error(exc) from None
    return InventoryTransactionListResponse(
        items=[_to_response(tx) for tx in page.items],
        next_cursor=page.next_cursor,
    )


@router.get("/{transaction_id}", response_model=InventoryTransactionResponse)
async def get_transaction(
    transaction_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(get_current_user)],
) -> InventoryTransactionResponse:
    try:
        tx = await transactions_service.get(session, transaction_id)
    except transactions_service.EntityNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="inventory transaction not found",
        ) from None
    return _to_response(tx)
