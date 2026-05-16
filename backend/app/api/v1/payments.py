"""Payments + credit/debit-notes API (Phase 7.4, #112).

Thin layer over ``app.services.payments`` / ``credit_notes`` /
``debit_notes``. Routers commit, map service errors to HTTP, and gate
each route on role:

* write (record / apply / cancel, draft + issue + apply + cancel
  credit/debit notes): owner + bookkeeper + sales
* read: + viewer
* **bookkeeper-only**: unapply, mark-bounced (financial reversal —
  matches the approvals model where bookkeeper is the financial role)
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_role
from app.core.db import get_session
from app.models.auth import User
from app.models.credit_note import CreditNote, DebitNote
from app.models.customer_credit import CustomerCreditBalance
from app.models.payment import Payment, PaymentApplication
from app.schemas.payments import (
    CreditNoteCreate,
    CreditNoteListResponse,
    CreditNoteResponse,
    CreditNoteUpdate,
    CustomerCreditBalanceResponse,
    DebitNoteCreate,
    DebitNoteListResponse,
    DebitNoteResponse,
    DebitNoteUpdate,
    PaymentApplicationResponse,
    PaymentApplyRequest,
    PaymentCreate,
    PaymentListResponse,
    PaymentResponse,
    PaymentTransitionRequest,
)
from app.services import credit_notes as credit_notes_service
from app.services import debit_notes as debit_notes_service
from app.services import payments as payments_service
from app.services.invoices import MissingArPostingAccountError

_WRITE_ROLES = ("owner", "bookkeeper", "sales")
_READ_ROLES = ("owner", "bookkeeper", "sales", "viewer")
_REVERSAL_ROLES = ("bookkeeper",)


payments_router = APIRouter(prefix="/payments", tags=["payments"])
credit_notes_router = APIRouter(prefix="/credit-notes", tags=["credit-notes"])
debit_notes_router = APIRouter(prefix="/debit-notes", tags=["debit-notes"])
customers_credit_router = APIRouter(prefix="/customers", tags=["customer-credit"])


# ---------------------------------------------------------------------------
# Conversion helpers
# ---------------------------------------------------------------------------


def _payment_to_response(payment: Payment) -> PaymentResponse:
    return PaymentResponse(
        id=payment.id,
        payment_number=payment.payment_number,
        customer_id=payment.customer_id,
        received_at=payment.received_at,
        method=payment.method.value,  # type: ignore[arg-type]
        reference=payment.reference,
        amount=payment.amount,
        state=payment.state.value,  # type: ignore[arg-type]
        notes=payment.notes,
        posting_journal_entry_id=payment.posting_journal_entry_id,
        created_by_user_id=payment.created_by_user_id,
        created_at=payment.created_at,
        updated_at=payment.updated_at,
        applications=[
            PaymentApplicationResponse(
                id=app_row.id,
                invoice_id=app_row.invoice_id,
                amount=app_row.amount,
                applied_at=app_row.applied_at,
            )
            for app_row in sorted(payment.applications, key=lambda a: a.applied_at)
        ],
    )


def _credit_note_to_response(note: CreditNote) -> CreditNoteResponse:
    return CreditNoteResponse(
        id=note.id,
        credit_note_number=note.credit_note_number,
        customer_id=note.customer_id,
        invoice_id=note.invoice_id,
        reason=note.reason,
        total_amount=note.total_amount,
        state=note.state.value,  # type: ignore[arg-type]
        notes=note.notes,
        posting_journal_entry_id=note.posting_journal_entry_id,
        created_by_user_id=note.created_by_user_id,
        created_at=note.created_at,
        updated_at=note.updated_at,
    )


def _debit_note_to_response(note: DebitNote) -> DebitNoteResponse:
    return DebitNoteResponse(
        id=note.id,
        debit_note_number=note.debit_note_number,
        customer_id=note.customer_id,
        invoice_id=note.invoice_id,
        reason=note.reason,
        total_amount=note.total_amount,
        state=note.state.value,  # type: ignore[arg-type]
        notes=note.notes,
        posting_journal_entry_id=note.posting_journal_entry_id,
        created_by_user_id=note.created_by_user_id,
        created_at=note.created_at,
        updated_at=note.updated_at,
    )


def _map_payment_error(exc: Exception) -> HTTPException:
    if isinstance(exc, payments_service.PaymentNotFoundError):
        return HTTPException(status_code=404, detail="payment not found")
    if isinstance(exc, MissingArPostingAccountError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, payments_service.PaymentsServiceError):
        return HTTPException(status_code=400, detail=str(exc))
    raise exc


def _map_credit_note_error(exc: Exception) -> HTTPException:
    if isinstance(exc, credit_notes_service.CreditNoteNotFoundError):
        return HTTPException(status_code=404, detail="credit note not found")
    if isinstance(exc, MissingArPostingAccountError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, credit_notes_service.CreditNoteServiceError):
        return HTTPException(status_code=400, detail=str(exc))
    raise exc


def _map_debit_note_error(exc: Exception) -> HTTPException:
    if isinstance(exc, debit_notes_service.DebitNoteNotFoundError):
        return HTTPException(status_code=404, detail="debit note not found")
    if isinstance(exc, MissingArPostingAccountError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, debit_notes_service.DebitNoteServiceError):
        return HTTPException(status_code=400, detail=str(exc))
    raise exc


# ---------------------------------------------------------------------------
# Payments
# ---------------------------------------------------------------------------


@payments_router.post("", response_model=PaymentResponse, status_code=status.HTTP_201_CREATED)
async def create_payment(
    payload: PaymentCreate,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role(*_WRITE_ROLES))],
) -> PaymentResponse:
    try:
        payment = await payments_service.record_payment(
            session,
            customer_id=payload.customer_id,
            amount=payload.amount,
            method=payload.method,
            reference=payload.reference,
            received_at=payload.received_at,
            notes=payload.notes,
            actor_user_id=actor.id,
        )
    except Exception as exc:
        await session.rollback()
        raise _map_payment_error(exc) from None
    await session.commit()
    payment = await payments_service.get(session, payment.id)
    return _payment_to_response(payment)


@payments_router.get("", response_model=PaymentListResponse)
async def list_payments(
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(require_role(*_READ_ROLES))],
    customer_id: Annotated[uuid.UUID | None, Query()] = None,
    state: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> PaymentListResponse:
    try:
        rows = await payments_service.list_payments(
            session, customer_id=customer_id, state=state, limit=limit
        )
    except Exception as exc:
        raise _map_payment_error(exc) from None
    return PaymentListResponse(items=[_payment_to_response(p) for p in rows])


@payments_router.get("/{payment_id}", response_model=PaymentResponse)
async def get_payment(
    payment_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(require_role(*_READ_ROLES))],
) -> PaymentResponse:
    try:
        payment = await payments_service.get(session, payment_id)
    except Exception as exc:
        raise _map_payment_error(exc) from None
    return _payment_to_response(payment)


@payments_router.post("/{payment_id}/apply", response_model=PaymentResponse)
async def apply_payment(
    payment_id: uuid.UUID,
    payload: PaymentApplyRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role(*_WRITE_ROLES))],
) -> PaymentResponse:
    try:
        await payments_service.apply_payment(
            session,
            payment_id=payment_id,
            applications=[(a.invoice_id, a.amount) for a in payload.applications],
            apply_excess_to_credit=payload.apply_excess_to_credit,
            actor_user_id=actor.id,
        )
    except Exception as exc:
        await session.rollback()
        raise _map_payment_error(exc) from None
    await session.commit()
    payment = await payments_service.get(session, payment_id)
    return _payment_to_response(payment)


@payments_router.post("/{payment_id}/unapply", response_model=PaymentResponse)
async def unapply_payment(
    payment_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role(*_REVERSAL_ROLES))],
    _payload: PaymentTransitionRequest | None = None,
) -> PaymentResponse:
    try:
        await payments_service.unapply_payment(
            session, payment_id=payment_id, actor_user_id=actor.id
        )
    except Exception as exc:
        await session.rollback()
        raise _map_payment_error(exc) from None
    await session.commit()
    payment = await payments_service.get(session, payment_id)
    return _payment_to_response(payment)


@payments_router.post("/{payment_id}/mark-bounced", response_model=PaymentResponse)
async def mark_bounced(
    payment_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role(*_REVERSAL_ROLES))],
    _payload: PaymentTransitionRequest | None = None,
) -> PaymentResponse:
    try:
        await payments_service.mark_bounced(session, payment_id=payment_id, actor_user_id=actor.id)
    except Exception as exc:
        await session.rollback()
        raise _map_payment_error(exc) from None
    await session.commit()
    payment = await payments_service.get(session, payment_id)
    return _payment_to_response(payment)


@payments_router.post("/{payment_id}/cancel", response_model=PaymentResponse)
async def cancel_payment(
    payment_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role(*_WRITE_ROLES))],
    _payload: PaymentTransitionRequest | None = None,
) -> PaymentResponse:
    try:
        await payments_service.cancel(session, payment_id=payment_id, actor_user_id=actor.id)
    except Exception as exc:
        await session.rollback()
        raise _map_payment_error(exc) from None
    await session.commit()
    payment = await payments_service.get(session, payment_id)
    return _payment_to_response(payment)


# ---------------------------------------------------------------------------
# Credit notes
# ---------------------------------------------------------------------------


@credit_notes_router.post(
    "", response_model=CreditNoteResponse, status_code=status.HTTP_201_CREATED
)
async def create_credit_note(
    payload: CreditNoteCreate,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role(*_WRITE_ROLES))],
) -> CreditNoteResponse:
    try:
        note = await credit_notes_service.create_draft(
            session,
            invoice_id=payload.invoice_id,
            total_amount=payload.total_amount,
            reason=payload.reason,
            notes=payload.notes,
            actor_user_id=actor.id,
        )
    except Exception as exc:
        await session.rollback()
        raise _map_credit_note_error(exc) from None
    await session.commit()
    note = await credit_notes_service.get(session, note.id)
    return _credit_note_to_response(note)


@credit_notes_router.get("", response_model=CreditNoteListResponse)
async def list_credit_notes(
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(require_role(*_READ_ROLES))],
    customer_id: Annotated[uuid.UUID | None, Query()] = None,
    invoice_id: Annotated[uuid.UUID | None, Query()] = None,
    state: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> CreditNoteListResponse:
    try:
        rows = await credit_notes_service.list_credit_notes(
            session,
            customer_id=customer_id,
            invoice_id=invoice_id,
            state=state,
            limit=limit,
        )
    except Exception as exc:
        raise _map_credit_note_error(exc) from None
    return CreditNoteListResponse(items=[_credit_note_to_response(n) for n in rows])


@credit_notes_router.get("/{credit_note_id}", response_model=CreditNoteResponse)
async def get_credit_note(
    credit_note_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(require_role(*_READ_ROLES))],
) -> CreditNoteResponse:
    try:
        note = await credit_notes_service.get(session, credit_note_id)
    except Exception as exc:
        raise _map_credit_note_error(exc) from None
    return _credit_note_to_response(note)


@credit_notes_router.patch("/{credit_note_id}", response_model=CreditNoteResponse)
async def update_credit_note(
    credit_note_id: uuid.UUID,
    payload: CreditNoteUpdate,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role(*_WRITE_ROLES))],
) -> CreditNoteResponse:
    try:
        await credit_notes_service.update_draft(
            session,
            credit_note_id=credit_note_id,
            patch=payload.model_dump(exclude_unset=True),
            actor_user_id=actor.id,
        )
    except Exception as exc:
        await session.rollback()
        raise _map_credit_note_error(exc) from None
    await session.commit()
    note = await credit_notes_service.get(session, credit_note_id)
    return _credit_note_to_response(note)


@credit_notes_router.post("/{credit_note_id}/issue", response_model=CreditNoteResponse)
async def issue_credit_note(
    credit_note_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role(*_WRITE_ROLES))],
) -> CreditNoteResponse:
    try:
        await credit_notes_service.issue(
            session, credit_note_id=credit_note_id, actor_user_id=actor.id
        )
    except Exception as exc:
        await session.rollback()
        raise _map_credit_note_error(exc) from None
    await session.commit()
    note = await credit_notes_service.get(session, credit_note_id)
    return _credit_note_to_response(note)


@credit_notes_router.post("/{credit_note_id}/apply", response_model=CreditNoteResponse)
async def apply_credit_note(
    credit_note_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role(*_WRITE_ROLES))],
) -> CreditNoteResponse:
    try:
        await credit_notes_service.apply(
            session, credit_note_id=credit_note_id, actor_user_id=actor.id
        )
    except Exception as exc:
        await session.rollback()
        raise _map_credit_note_error(exc) from None
    await session.commit()
    note = await credit_notes_service.get(session, credit_note_id)
    return _credit_note_to_response(note)


@credit_notes_router.post("/{credit_note_id}/cancel", response_model=CreditNoteResponse)
async def cancel_credit_note(
    credit_note_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role(*_WRITE_ROLES))],
) -> CreditNoteResponse:
    try:
        await credit_notes_service.cancel(
            session, credit_note_id=credit_note_id, actor_user_id=actor.id
        )
    except Exception as exc:
        await session.rollback()
        raise _map_credit_note_error(exc) from None
    await session.commit()
    note = await credit_notes_service.get(session, credit_note_id)
    return _credit_note_to_response(note)


# ---------------------------------------------------------------------------
# Debit notes
# ---------------------------------------------------------------------------


@debit_notes_router.post("", response_model=DebitNoteResponse, status_code=status.HTTP_201_CREATED)
async def create_debit_note(
    payload: DebitNoteCreate,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role(*_WRITE_ROLES))],
) -> DebitNoteResponse:
    try:
        note = await debit_notes_service.create_draft(
            session,
            invoice_id=payload.invoice_id,
            total_amount=payload.total_amount,
            reason=payload.reason,
            notes=payload.notes,
            actor_user_id=actor.id,
        )
    except Exception as exc:
        await session.rollback()
        raise _map_debit_note_error(exc) from None
    await session.commit()
    note = await debit_notes_service.get(session, note.id)
    return _debit_note_to_response(note)


@debit_notes_router.get("", response_model=DebitNoteListResponse)
async def list_debit_notes(
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(require_role(*_READ_ROLES))],
    customer_id: Annotated[uuid.UUID | None, Query()] = None,
    invoice_id: Annotated[uuid.UUID | None, Query()] = None,
    state: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> DebitNoteListResponse:
    try:
        rows = await debit_notes_service.list_debit_notes(
            session,
            customer_id=customer_id,
            invoice_id=invoice_id,
            state=state,
            limit=limit,
        )
    except Exception as exc:
        raise _map_debit_note_error(exc) from None
    return DebitNoteListResponse(items=[_debit_note_to_response(n) for n in rows])


@debit_notes_router.get("/{debit_note_id}", response_model=DebitNoteResponse)
async def get_debit_note(
    debit_note_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(require_role(*_READ_ROLES))],
) -> DebitNoteResponse:
    try:
        note = await debit_notes_service.get(session, debit_note_id)
    except Exception as exc:
        raise _map_debit_note_error(exc) from None
    return _debit_note_to_response(note)


@debit_notes_router.patch("/{debit_note_id}", response_model=DebitNoteResponse)
async def update_debit_note(
    debit_note_id: uuid.UUID,
    payload: DebitNoteUpdate,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role(*_WRITE_ROLES))],
) -> DebitNoteResponse:
    try:
        await debit_notes_service.update_draft(
            session,
            debit_note_id=debit_note_id,
            patch=payload.model_dump(exclude_unset=True),
            actor_user_id=actor.id,
        )
    except Exception as exc:
        await session.rollback()
        raise _map_debit_note_error(exc) from None
    await session.commit()
    note = await debit_notes_service.get(session, debit_note_id)
    return _debit_note_to_response(note)


@debit_notes_router.post("/{debit_note_id}/issue", response_model=DebitNoteResponse)
async def issue_debit_note(
    debit_note_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role(*_WRITE_ROLES))],
) -> DebitNoteResponse:
    try:
        await debit_notes_service.issue(
            session, debit_note_id=debit_note_id, actor_user_id=actor.id
        )
    except Exception as exc:
        await session.rollback()
        raise _map_debit_note_error(exc) from None
    await session.commit()
    note = await debit_notes_service.get(session, debit_note_id)
    return _debit_note_to_response(note)


@debit_notes_router.post("/{debit_note_id}/apply", response_model=DebitNoteResponse)
async def apply_debit_note(
    debit_note_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role(*_WRITE_ROLES))],
) -> DebitNoteResponse:
    try:
        await debit_notes_service.apply(
            session, debit_note_id=debit_note_id, actor_user_id=actor.id
        )
    except Exception as exc:
        await session.rollback()
        raise _map_debit_note_error(exc) from None
    await session.commit()
    note = await debit_notes_service.get(session, debit_note_id)
    return _debit_note_to_response(note)


@debit_notes_router.post("/{debit_note_id}/cancel", response_model=DebitNoteResponse)
async def cancel_debit_note(
    debit_note_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role(*_WRITE_ROLES))],
) -> DebitNoteResponse:
    try:
        await debit_notes_service.cancel(
            session, debit_note_id=debit_note_id, actor_user_id=actor.id
        )
    except Exception as exc:
        await session.rollback()
        raise _map_debit_note_error(exc) from None
    await session.commit()
    note = await debit_notes_service.get(session, debit_note_id)
    return _debit_note_to_response(note)


# ---------------------------------------------------------------------------
# Customer credit balance (read-only projection)
# ---------------------------------------------------------------------------


@customers_credit_router.get(
    "/{customer_id}/credit-balance", response_model=CustomerCreditBalanceResponse
)
async def get_customer_credit_balance(
    customer_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(require_role(*_READ_ROLES))],
) -> CustomerCreditBalanceResponse:
    row = (
        await session.execute(
            select(CustomerCreditBalance).where(CustomerCreditBalance.customer_id == customer_id)
        )
    ).scalar_one_or_none()
    if row is None:
        # Projection hasn't materialized a row yet — return zero. The
        # spec calls for a read-only projection endpoint and it's
        # explicit that brand-new customers have no row until their
        # first accrual.
        from decimal import Decimal as _D

        return CustomerCreditBalanceResponse(
            customer_id=customer_id,
            available_amount=_D("0"),
            updated_at=None,
        )
    return CustomerCreditBalanceResponse(
        customer_id=row.customer_id,
        available_amount=row.available_amount,
        updated_at=row.updated_at,
    )


# Re-exports so the v1 router can import a single name per module.
# Suppress F401 for these names.
__all__ = [
    "credit_notes_router",
    "customers_credit_router",
    "debit_notes_router",
    "payments_router",
]


# Silence unused-import lint for PaymentApplication (referenced by
# from_orm-style code paths via _payment_to_response).
_ = PaymentApplication
