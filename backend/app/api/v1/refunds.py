"""Refunds API (Phase 6.5, #97).

Thin layer over ``app.services.refunds``. Routers commit the
transaction, map service-layer errors to HTTP, and gate each route on
role:

* create / cancel: sales + owner
* approve / reject: owner only
* post: owner + sales
* read: sales + owner + bookkeeper
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_role
from app.core.db import get_session
from app.models.auth import User
from app.models.refund import Refund, RefundItem, RefundKind, RefundState
from app.schemas.refunds import (
    RefundApprovalDecision,
    RefundCreate,
    RefundCreateResponse,
    RefundItemResponse,
    RefundListResponse,
    RefundResponse,
)
from app.services import refunds as refunds_service

router = APIRouter(prefix="/refunds", tags=["refunds"])


def _to_item(item: RefundItem) -> RefundItemResponse:
    return RefundItemResponse(
        id=item.id,
        sale_item_id=item.sale_item_id,
        quantity=item.quantity,
        unit_amount=item.unit_amount,
        extended_amount=item.extended_amount,
    )


def _to_response(refund: Refund) -> RefundResponse:
    return RefundResponse(
        id=refund.id,
        refund_number=refund.refund_number,
        sale_id=refund.sale_id,
        kind=(refund.kind.value if isinstance(refund.kind, RefundKind) else refund.kind),  # type: ignore[arg-type]
        state=(refund.state.value if isinstance(refund.state, RefundState) else refund.state),  # type: ignore[arg-type]
        total_amount=refund.total_amount,
        restock_inventory=refund.restock_inventory,
        reason_code=refund.reason_code,
        notes=refund.notes,
        created_by_user_id=refund.created_by_user_id,
        approved_by_user_id=refund.approved_by_user_id,
        approval_request_id=refund.approval_request_id,
        posting_journal_entry_id=refund.posting_journal_entry_id,
        created_at=refund.created_at,
        updated_at=refund.updated_at,
        items=[_to_item(i) for i in refund.items],
    )


def _map_error(exc: Exception) -> HTTPException:
    if isinstance(exc, refunds_service.RefundNotFoundError):
        return HTTPException(status_code=404, detail="refund not found")
    if isinstance(exc, refunds_service.SaleNotFoundForRefundError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, refunds_service.OverRefundError):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, refunds_service.InvalidRefundItemError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, refunds_service.InvalidRefundStateError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, refunds_service.InvalidCursorError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, refunds_service.RefundsServiceError):
        return HTTPException(status_code=400, detail=str(exc))
    raise exc


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


@router.post("", response_model=RefundCreateResponse)
async def create_refund(
    payload: RefundCreate,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role("owner", "sales"))],
) -> RefundCreateResponse:
    try:
        result = await refunds_service.create(
            session=session,
            sale_id=payload.sale_id,
            kind=payload.kind,
            reason_code=payload.reason_code,
            notes=payload.notes,
            restock_inventory=payload.restock_inventory,
            items=[item.model_dump() for item in payload.items],
            actor_user_id=actor.id,
        )
    except Exception as exc:
        await session.rollback()
        raise _map_error(exc) from None
    await session.commit()
    refund = await refunds_service.get(result.refund.id, session=session)
    if result.approval_request_id is not None:
        response.status_code = status.HTTP_202_ACCEPTED
    else:
        response.status_code = status.HTTP_201_CREATED
    return RefundCreateResponse(
        refund=_to_response(refund),
        approval_request_id=result.approval_request_id,
    )


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------


@router.get("", response_model=RefundListResponse)
async def list_refunds(
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(require_role("owner", "bookkeeper", "sales"))],
    state: Annotated[str | None, Query()] = None,
    sale_id: Annotated[uuid.UUID | None, Query()] = None,
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> RefundListResponse:
    try:
        page = await refunds_service.list_refunds(
            session=session,
            state=state,
            sale_id=sale_id,
            cursor=cursor,
            limit=limit,
        )
    except Exception as exc:
        raise _map_error(exc) from None
    return RefundListResponse(
        items=[_to_response(r) for r in page.items],
        next_cursor=page.next_cursor,
    )


@router.get("/{refund_id}", response_model=RefundResponse)
async def get_refund(
    refund_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(require_role("owner", "bookkeeper", "sales"))],
) -> RefundResponse:
    try:
        refund = await refunds_service.get(refund_id, session=session)
    except Exception as exc:
        raise _map_error(exc) from None
    return _to_response(refund)


# ---------------------------------------------------------------------------
# Approve / reject / cancel / post
# ---------------------------------------------------------------------------


@router.post("/{refund_id}/approve", response_model=RefundResponse)
async def approve_refund(
    refund_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role("owner"))],
    payload: RefundApprovalDecision | None = None,
) -> RefundResponse:
    try:
        await refunds_service.approve(
            refund_id,
            session=session,
            actor_user_id=actor.id,
            decision_note=payload.note if payload else None,
        )
    except Exception as exc:
        await session.rollback()
        raise _map_error(exc) from None
    await session.commit()
    refund = await refunds_service.get(refund_id, session=session)
    return _to_response(refund)


@router.post("/{refund_id}/reject", response_model=RefundResponse)
async def reject_refund(
    refund_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role("owner"))],
    payload: RefundApprovalDecision | None = None,
) -> RefundResponse:
    try:
        await refunds_service.reject(
            refund_id,
            session=session,
            actor_user_id=actor.id,
            decision_note=payload.note if payload else None,
        )
    except Exception as exc:
        await session.rollback()
        raise _map_error(exc) from None
    await session.commit()
    refund = await refunds_service.get(refund_id, session=session)
    return _to_response(refund)


@router.post("/{refund_id}/cancel", response_model=RefundResponse)
async def cancel_refund(
    refund_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role("owner", "sales"))],
) -> RefundResponse:
    try:
        await refunds_service.cancel(refund_id, session=session, actor_user_id=actor.id)
    except Exception as exc:
        await session.rollback()
        raise _map_error(exc) from None
    await session.commit()
    refund = await refunds_service.get(refund_id, session=session)
    return _to_response(refund)


@router.post("/{refund_id}/post", response_model=RefundResponse)
async def post_refund(
    refund_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role("owner", "sales"))],
) -> RefundResponse:
    try:
        await refunds_service.post(refund_id, session=session, actor_user_id=actor.id)
    except Exception as exc:
        await session.rollback()
        raise _map_error(exc) from None
    await session.commit()
    refund = await refunds_service.get(refund_id, session=session)
    return _to_response(refund)
