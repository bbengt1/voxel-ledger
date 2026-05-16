"""Bill payments API (Phase 8.3, #130).

Thin layer over ``app.services.bill_payments`` — the AP-side mirror of
the Phase 7.4 AR ``payments`` router. Routers commit, map service
errors to HTTP, and gate each route on role:

* write (record / unapply / bounce / cancel): owner + bookkeeper
* read: + sales + viewer
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
from app.models.bill_payment import BillPayment
from app.schemas.bill_payments import (
    BillPaymentApplicationResponse,
    BillPaymentCreate,
    BillPaymentListResponse,
    BillPaymentResponse,
    BillPaymentTransitionRequest,
)
from app.services import bill_payments as bill_payments_service

_WRITE_ROLES = ("owner", "bookkeeper")
_READ_ROLES = ("owner", "bookkeeper", "sales", "viewer")


bill_payments_router = APIRouter(prefix="/bill-payments", tags=["bill-payments"])


def _to_response(payment: BillPayment) -> BillPaymentResponse:
    return BillPaymentResponse(
        id=payment.id,
        payment_number=payment.payment_number,
        vendor_id=payment.vendor_id,
        method=payment.method.value,  # type: ignore[arg-type]
        amount=payment.amount,
        occurred_at=payment.occurred_at,
        reference_number=payment.reference_number,
        notes=payment.notes,
        state=payment.state.value,  # type: ignore[arg-type]
        posting_journal_entry_id=payment.posting_journal_entry_id,
        created_by_user_id=payment.created_by_user_id,
        created_at=payment.created_at,
        updated_at=payment.updated_at,
        applications=[
            BillPaymentApplicationResponse(
                id=app_row.id,
                bill_id=app_row.bill_id,
                amount_applied=app_row.amount_applied,
                created_at=app_row.created_at,
                updated_at=app_row.updated_at,
            )
            for app_row in sorted(payment.applications, key=lambda a: a.created_at)
        ],
    )


def _map_error(exc: Exception) -> HTTPException:
    if isinstance(exc, bill_payments_service.BillPaymentNotFoundError):
        return HTTPException(status_code=404, detail="bill payment not found")
    if isinstance(exc, bill_payments_service.VendorNotFoundForBillPaymentError):
        return HTTPException(status_code=400, detail=f"vendor not found: {exc}")
    if isinstance(exc, bill_payments_service.BillNotFoundForApplicationError):
        return HTTPException(status_code=400, detail=f"bill not found: {exc}")
    if isinstance(exc, bill_payments_service.MissingApPostingAccountError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, bill_payments_service.VendorArchivedError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, bill_payments_service.InvalidBillPaymentAmountError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, bill_payments_service.InvalidBillPaymentStateError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, bill_payments_service.OverApplicationError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, bill_payments_service.InvalidCursorError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, bill_payments_service.BillPaymentsServiceError):
        return HTTPException(status_code=400, detail=str(exc))
    raise exc


@bill_payments_router.post(
    "", response_model=BillPaymentResponse, status_code=status.HTTP_201_CREATED
)
async def record_bill_payment(
    payload: BillPaymentCreate,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role(*_WRITE_ROLES))],
) -> BillPaymentResponse:
    try:
        payment = await bill_payments_service.record_payment(
            session,
            vendor_id=payload.vendor_id,
            method=payload.method,
            amount=payload.amount,
            occurred_at=payload.occurred_at,
            reference_number=payload.reference_number,
            notes=payload.notes,
            applications=[(a.bill_id, a.amount_applied) for a in payload.applications],
            actor_user_id=actor.id,
        )
    except Exception as exc:
        await session.rollback()
        raise _map_error(exc) from None
    await session.commit()
    payment = await bill_payments_service.get(session, payment.id)
    return _to_response(payment)


@bill_payments_router.get("", response_model=BillPaymentListResponse)
async def list_bill_payments(
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(require_role(*_READ_ROLES))],
    vendor_id: Annotated[uuid.UUID | None, Query()] = None,
    state: Annotated[str | None, Query()] = None,
    date_from: Annotated[datetime | None, Query()] = None,
    date_to: Annotated[datetime | None, Query()] = None,
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> BillPaymentListResponse:
    try:
        rows, next_cursor = await bill_payments_service.list_bill_payments(
            session,
            vendor_id=vendor_id,
            state=state,
            date_from=date_from,
            date_to=date_to,
            cursor=cursor,
            limit=limit,
        )
    except Exception as exc:
        raise _map_error(exc) from None
    return BillPaymentListResponse(items=[_to_response(p) for p in rows], next_cursor=next_cursor)


@bill_payments_router.get("/{bill_payment_id}", response_model=BillPaymentResponse)
async def get_bill_payment(
    bill_payment_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(require_role(*_READ_ROLES))],
) -> BillPaymentResponse:
    try:
        payment = await bill_payments_service.get(session, bill_payment_id)
    except Exception as exc:
        raise _map_error(exc) from None
    return _to_response(payment)


@bill_payments_router.post("/{bill_payment_id}/unapply", response_model=BillPaymentResponse)
async def unapply_bill_payment(
    bill_payment_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role(*_WRITE_ROLES))],
    _payload: BillPaymentTransitionRequest | None = None,
) -> BillPaymentResponse:
    try:
        await bill_payments_service.unapply(
            session, bill_payment_id=bill_payment_id, actor_user_id=actor.id
        )
    except Exception as exc:
        await session.rollback()
        raise _map_error(exc) from None
    await session.commit()
    payment = await bill_payments_service.get(session, bill_payment_id)
    return _to_response(payment)


@bill_payments_router.post("/{bill_payment_id}/bounce", response_model=BillPaymentResponse)
async def bounce_bill_payment(
    bill_payment_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role(*_WRITE_ROLES))],
    _payload: BillPaymentTransitionRequest | None = None,
) -> BillPaymentResponse:
    try:
        await bill_payments_service.bounce(
            session, bill_payment_id=bill_payment_id, actor_user_id=actor.id
        )
    except Exception as exc:
        await session.rollback()
        raise _map_error(exc) from None
    await session.commit()
    payment = await bill_payments_service.get(session, bill_payment_id)
    return _to_response(payment)


@bill_payments_router.post("/{bill_payment_id}/cancel", response_model=BillPaymentResponse)
async def cancel_bill_payment(
    bill_payment_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role(*_WRITE_ROLES))],
    _payload: BillPaymentTransitionRequest | None = None,
) -> BillPaymentResponse:
    try:
        await bill_payments_service.cancel(
            session, bill_payment_id=bill_payment_id, actor_user_id=actor.id
        )
    except Exception as exc:
        await session.rollback()
        raise _map_error(exc) from None
    await session.commit()
    payment = await bill_payments_service.get(session, bill_payment_id)
    return _to_response(payment)


__all__ = ["bill_payments_router"]
