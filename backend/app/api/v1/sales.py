"""Sales API (Phase 6.2, #94).

Thin layer over ``app.services.sales``. Routers commit the transaction,
map service-layer errors to HTTP, and gate each route on role:

* write (create / update / state transitions): owner + bookkeeper + sales
* read (list / get): owner + bookkeeper + sales + viewer
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_role
from app.core.db import get_session
from app.models.auth import User
from app.models.sale import Sale, SaleItem, SaleItemKind
from app.schemas.sales import (
    SaleCreate,
    SaleItemResponse,
    SaleListResponse,
    SaleResponse,
    SaleStateTransitionRequest,
    SaleUpdate,
)
from app.services import sales as sales_service

router = APIRouter(prefix="/sales", tags=["sales"])


def _to_item(item: SaleItem) -> SaleItemResponse:
    return SaleItemResponse(
        id=item.id,
        line_number=item.line_number,
        kind=(item.kind.value if isinstance(item.kind, SaleItemKind) else item.kind),  # type: ignore[arg-type]
        product_id=item.product_id,
        job_id=item.job_id,
        description=item.description,
        sku_or_job_number=item.sku_or_job_number,
        quantity=item.quantity,
        unit_price=item.unit_price,
        extended_amount=item.extended_amount,
    )


def _to_response(sale: Sale) -> SaleResponse:
    return SaleResponse(
        id=sale.id,
        sale_number=sale.sale_number,
        channel_id=sale.channel_id,
        external_order_id=sale.external_order_id,
        customer_name=sale.customer_name,
        customer_email=sale.customer_email,
        occurred_at=sale.occurred_at,
        recorded_at=sale.recorded_at,
        subtotal=sale.subtotal,
        discount_amount=sale.discount_amount,
        shipping_amount=sale.shipping_amount,
        tax_amount=sale.tax_amount,
        channel_fee_amount=sale.channel_fee_amount,
        total_amount=sale.total_amount,
        state=sale.state.value,  # type: ignore[arg-type]
        notes=sale.notes,
        created_by_user_id=sale.created_by_user_id,
        created_at=sale.created_at,
        updated_at=sale.updated_at,
        items=[_to_item(i) for i in sorted(sale.items, key=lambda x: x.line_number)],
    )


def _map_error(exc: Exception) -> HTTPException:
    if isinstance(exc, sales_service.SaleNotFoundError):
        return HTTPException(status_code=404, detail="sale not found")
    if isinstance(exc, sales_service.SalesChannelNotFoundError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, sales_service.InvalidSaleItemError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, sales_service.InvalidSaleStateError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, sales_service.InvalidCursorError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, sales_service.SalesServiceError):
        return HTTPException(status_code=400, detail=str(exc))
    raise exc


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


@router.post("", response_model=SaleResponse, status_code=status.HTTP_201_CREATED)
async def create_sale(
    payload: SaleCreate,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role("owner", "bookkeeper", "sales"))],
) -> SaleResponse:
    try:
        sale = await sales_service.create_draft(
            session,
            channel_id=payload.channel_id,
            external_order_id=payload.external_order_id,
            customer_name=payload.customer_name,
            customer_email=payload.customer_email,
            occurred_at=payload.occurred_at,
            discount_amount=payload.discount_amount,
            shipping_amount=payload.shipping_amount,
            tax_amount=payload.tax_amount,
            notes=payload.notes,
            items=[item.model_dump() for item in payload.items],
            actor_user_id=actor.id,
        )
    except Exception as exc:
        await session.rollback()
        raise _map_error(exc) from None
    await session.commit()
    sale = await sales_service.get(session, sale.id)
    return _to_response(sale)


@router.get("", response_model=SaleListResponse)
async def list_sales(
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(require_role("owner", "bookkeeper", "sales", "viewer"))],
    state: Annotated[str | None, Query()] = None,
    channel_id: Annotated[uuid.UUID | None, Query()] = None,
    search: Annotated[str | None, Query()] = None,
    date_from: Annotated[datetime | None, Query()] = None,
    date_to: Annotated[datetime | None, Query()] = None,
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> SaleListResponse:
    try:
        page = await sales_service.list_sales(
            session,
            state=state,
            channel_id=channel_id,
            search=search,
            date_from=date_from,
            date_to=date_to,
            cursor=cursor,
            limit=limit,
        )
    except Exception as exc:
        raise _map_error(exc) from None
    return SaleListResponse(
        items=[_to_response(s) for s in page.items],
        next_cursor=page.next_cursor,
    )


@router.get("/{sale_id}", response_model=SaleResponse)
async def get_sale(
    sale_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(require_role("owner", "bookkeeper", "sales", "viewer"))],
) -> SaleResponse:
    try:
        sale = await sales_service.get(session, sale_id)
    except Exception as exc:
        raise _map_error(exc) from None
    return _to_response(sale)


@router.patch("/{sale_id}", response_model=SaleResponse)
async def update_sale(
    sale_id: uuid.UUID,
    payload: SaleUpdate,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role("owner", "bookkeeper", "sales"))],
) -> SaleResponse:
    patch_dict = payload.model_dump(exclude_unset=True)
    if "items" in patch_dict and patch_dict["items"] is not None:
        patch_dict["items"] = [item for item in patch_dict["items"]]
    try:
        await sales_service.update_draft(
            session, sale_id=sale_id, patch=patch_dict, actor_user_id=actor.id
        )
    except Exception as exc:
        await session.rollback()
        raise _map_error(exc) from None
    await session.commit()
    sale = await sales_service.get(session, sale_id)
    return _to_response(sale)


# ---------------------------------------------------------------------------
# State transitions
# ---------------------------------------------------------------------------


@router.post("/{sale_id}/confirm", response_model=SaleResponse)
async def confirm_sale(
    sale_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role("owner", "bookkeeper", "sales"))],
    _payload: SaleStateTransitionRequest | None = None,
) -> SaleResponse:
    try:
        await sales_service.confirm(session, sale_id=sale_id, actor_user_id=actor.id)
    except Exception as exc:
        await session.rollback()
        raise _map_error(exc) from None
    await session.commit()
    sale = await sales_service.get(session, sale_id)
    return _to_response(sale)


@router.post("/{sale_id}/fulfill", response_model=SaleResponse)
async def fulfill_sale(
    sale_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role("owner", "bookkeeper", "sales"))],
    _payload: SaleStateTransitionRequest | None = None,
) -> SaleResponse:
    try:
        await sales_service.fulfill(session, sale_id=sale_id, actor_user_id=actor.id)
    except Exception as exc:
        await session.rollback()
        raise _map_error(exc) from None
    await session.commit()
    sale = await sales_service.get(session, sale_id)
    return _to_response(sale)


@router.post("/{sale_id}/cancel", response_model=SaleResponse)
async def cancel_sale(
    sale_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role("owner", "bookkeeper", "sales"))],
    _payload: SaleStateTransitionRequest | None = None,
) -> SaleResponse:
    try:
        await sales_service.cancel(session, sale_id=sale_id, actor_user_id=actor.id)
    except Exception as exc:
        await session.rollback()
        raise _map_error(exc) from None
    await session.commit()
    sale = await sales_service.get(session, sale_id)
    return _to_response(sale)
