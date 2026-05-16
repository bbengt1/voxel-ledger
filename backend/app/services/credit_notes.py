"""Credit-notes service (Phase 7.4, #112).

A credit note is a post-issue correction that reduces what the customer
owes on an already-issued invoice. Issuing posts ``debit Revenue /
credit AR`` for the credit-note total (proportional reversal of a slice
of the invoice's original revenue posting). Applying reduces the
target invoice's ``amount_outstanding`` without a real payment.

State machine: ``draft -> issued -> applied | cancelled``.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.events.types import ar as ar_events
from app.models.credit_note import CreditNote, CreditNoteState
from app.models.invoice import Invoice, InvoiceState
from app.models.journal_entry import JournalEntry
from app.schemas.events import EventCreate
from app.services import event_store
from app.services import journal_entries as journal_service
from app.services.invoices import (
    _resolve_ar_account as _resolve_invoice_ar_account,
)
from app.services.invoices import (
    _resolve_revenue_account as _resolve_invoice_revenue_account,
)
from app.services.reference_number import ReferenceNumberService

# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class CreditNoteServiceError(Exception):
    """Base. Routers map to 400 unless noted."""


class CreditNoteNotFoundError(CreditNoteServiceError):
    """404."""


class InvalidCreditNoteStateError(CreditNoteServiceError):
    pass


class InvalidCreditNoteAmountError(CreditNoteServiceError):
    pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_QUANTUM = Decimal("0.000001")
_ZERO = Decimal("0")


def _q(value: Decimal | str | int | float) -> Decimal:
    if not isinstance(value, Decimal):
        value = Decimal(str(value))
    return value.quantize(_QUANTUM, rounding=ROUND_HALF_UP)


async def _load(session: AsyncSession, credit_note_id: uuid.UUID) -> CreditNote:
    row = (
        await session.execute(select(CreditNote).where(CreditNote.id == credit_note_id))
    ).scalar_one_or_none()
    if row is None:
        raise CreditNoteNotFoundError(str(credit_note_id))
    return row


async def _load_invoice(session: AsyncSession, invoice_id: uuid.UUID) -> Invoice:
    row = (
        await session.execute(select(Invoice).where(Invoice.id == invoice_id))
    ).scalar_one_or_none()
    if row is None:
        raise CreditNoteServiceError(f"invoice {invoice_id} not found")
    return row


async def _emit(
    session: AsyncSession,
    *,
    event_type: str,
    aggregate_id: uuid.UUID,
    payload: dict[str, Any],
    actor_user_id: uuid.UUID | None,
) -> None:
    await event_store.append(
        EventCreate(
            type=event_type,
            aggregate_type=ar_events.AGGREGATE_TYPE_CREDIT_NOTE,
            aggregate_id=aggregate_id,
            payload=payload,
            occurred_at=datetime.now(UTC),
            correlation_id=uuid.uuid4(),
            actor_user_id=actor_user_id,
        ),
        session=session,
    )


# ---------------------------------------------------------------------------
# CRUD / state transitions
# ---------------------------------------------------------------------------


async def create_draft(
    session: AsyncSession,
    *,
    invoice_id: uuid.UUID,
    total_amount: Decimal | str | int | float,
    reason: str = "",
    notes: str | None = None,
    actor_user_id: uuid.UUID,
) -> CreditNote:
    invoice = await _load_invoice(session, invoice_id)
    amt = _q(total_amount)
    if amt <= _ZERO:
        raise InvalidCreditNoteAmountError("credit note total must be > 0")
    if amt > _q(invoice.total_amount):
        raise InvalidCreditNoteAmountError(
            f"credit note total {amt} exceeds invoice total {invoice.total_amount}"
        )

    number = await ReferenceNumberService.allocate("CN", session=session)
    note = CreditNote(
        credit_note_number=number,
        customer_id=invoice.customer_id,
        invoice_id=invoice.id,
        reason=reason,
        total_amount=amt,
        state=CreditNoteState.DRAFT,
        notes=notes,
        created_by_user_id=actor_user_id,
    )
    session.add(note)
    await session.flush()

    await _emit(
        session,
        event_type=ar_events.TYPE_CREDIT_NOTE_CREATED,
        aggregate_id=note.id,
        payload={
            "credit_note_id": str(note.id),
            "credit_note_number": number,
            "customer_id": str(invoice.customer_id),
            "invoice_id": str(invoice.id),
            "reason": reason,
            "total_amount": str(amt),
            "state": note.state.value,
        },
        actor_user_id=actor_user_id,
    )
    return note


async def update_draft(
    session: AsyncSession,
    *,
    credit_note_id: uuid.UUID,
    patch: dict[str, Any],
    actor_user_id: uuid.UUID,
) -> CreditNote:
    note = await _load(session, credit_note_id)
    if note.state != CreditNoteState.DRAFT:
        raise InvalidCreditNoteStateError(f"credit note {note.credit_note_number} is not a draft")
    before: dict[str, Any] = {}
    after: dict[str, Any] = {}
    for field in ("reason", "notes", "total_amount"):
        if field not in patch:
            continue
        new = patch[field]
        if field == "total_amount":
            new = _q(new)
            if new <= _ZERO:
                raise InvalidCreditNoteAmountError("credit note total must be > 0")
        current = getattr(note, field)
        if current == new:
            continue
        before[field] = str(current) if isinstance(current, Decimal) else current
        after[field] = str(new) if isinstance(new, Decimal) else new
        setattr(note, field, new)
    if not before:
        return note
    await session.flush()
    await _emit(
        session,
        event_type=ar_events.TYPE_CREDIT_NOTE_UPDATED,
        aggregate_id=note.id,
        payload={
            "credit_note_id": str(note.id),
            "before": before,
            "after": after,
        },
        actor_user_id=actor_user_id,
    )
    return note


async def issue(
    session: AsyncSession,
    *,
    credit_note_id: uuid.UUID,
    actor_user_id: uuid.UUID,
) -> CreditNote:
    note = await _load(session, credit_note_id)
    if note.state != CreditNoteState.DRAFT:
        raise InvalidCreditNoteStateError(f"credit note {note.credit_note_number} is not a draft")
    invoice = await _load_invoice(session, note.invoice_id)
    # Build customer ref for account resolution
    from app.models.customer import Customer

    customer = (
        await session.execute(select(Customer).where(Customer.id == note.customer_id))
    ).scalar_one()

    ar_account_id = await _resolve_invoice_ar_account(session, customer=customer)
    revenue_account_id = await _resolve_invoice_revenue_account(session, customer=customer)

    amt = _q(note.total_amount)
    lines = [
        journal_service.JournalLineInput(
            account_id=revenue_account_id,
            debit=amt,
            credit=_ZERO,
            line_number=1,
            memo=f"Credit note {note.credit_note_number} (rev reversal)",
        ),
        journal_service.JournalLineInput(
            account_id=ar_account_id,
            debit=_ZERO,
            credit=amt,
            line_number=2,
            memo=f"Credit note {note.credit_note_number} (AR reduction)",
        ),
    ]
    entry = await journal_service.post(
        journal_service.JournalEntryInput(
            description=f"Credit note {note.credit_note_number}",
            posted_at=datetime.now(UTC),
            lines=lines,
        ),
        session=session,
        actor_user_id=actor_user_id,
        _internal_skip_approval_check=True,
    )
    assert isinstance(entry, JournalEntry)
    note.state = CreditNoteState.ISSUED
    note.posting_journal_entry_id = entry.id
    await session.flush()

    await _emit(
        session,
        event_type=ar_events.TYPE_CREDIT_NOTE_ISSUED,
        aggregate_id=note.id,
        payload={
            "credit_note_id": str(note.id),
            "credit_note_number": note.credit_note_number,
            "customer_id": str(note.customer_id),
            "invoice_id": str(invoice.id),
            "total_amount": str(amt),
            "journal_entry_id": str(entry.id),
        },
        actor_user_id=actor_user_id,
    )
    return note


async def apply(
    session: AsyncSession,
    *,
    credit_note_id: uuid.UUID,
    actor_user_id: uuid.UUID,
) -> CreditNote:
    """Apply an issued credit note to its target invoice.

    Reduces invoice outstanding by the credit-note total (capped at
    outstanding). The GL was already moved at ``issue`` time; this step
    is the bookkeeping that reflects the credit on the customer's
    open-invoice list.
    """
    note = await _load(session, credit_note_id)
    if note.state != CreditNoteState.ISSUED:
        raise InvalidCreditNoteStateError(f"credit note {note.credit_note_number} is not issued")
    invoice = await _load_invoice(session, note.invoice_id)
    if invoice.state in (InvoiceState.DRAFT, InvoiceState.VOID):
        raise InvalidCreditNoteStateError(
            f"cannot apply credit note to invoice in state {invoice.state.value}"
        )
    amt = _q(note.total_amount)
    outstanding = _q(invoice.amount_outstanding)
    apply_amt = min(amt, outstanding)
    invoice.amount_paid = _q(invoice.amount_paid + apply_amt)
    invoice.amount_outstanding = _q(invoice.amount_outstanding - apply_amt)
    if invoice.amount_outstanding <= _ZERO and invoice.state != InvoiceState.PAID:
        invoice.state = InvoiceState.PAID
    elif invoice.amount_paid > _ZERO and invoice.state in (
        InvoiceState.ISSUED,
        InvoiceState.OVERDUE,
    ):
        invoice.state = InvoiceState.PARTIALLY_PAID
    note.state = CreditNoteState.APPLIED
    await session.flush()
    await _emit(
        session,
        event_type=ar_events.TYPE_CREDIT_NOTE_APPLIED,
        aggregate_id=note.id,
        payload={
            "credit_note_id": str(note.id),
            "credit_note_number": note.credit_note_number,
            "customer_id": str(note.customer_id),
            "invoice_id": str(invoice.id),
            "amount_applied": str(apply_amt),
        },
        actor_user_id=actor_user_id,
    )
    return note


async def cancel(
    session: AsyncSession,
    *,
    credit_note_id: uuid.UUID,
    actor_user_id: uuid.UUID,
) -> CreditNote:
    note = await _load(session, credit_note_id)
    if note.state == CreditNoteState.CANCELLED:
        return note
    if note.state == CreditNoteState.APPLIED:
        raise InvalidCreditNoteStateError(
            f"credit note {note.credit_note_number} is applied; cannot cancel"
        )
    reversing_je_id: uuid.UUID | None = None
    if note.state == CreditNoteState.ISSUED and note.posting_journal_entry_id is not None:
        reversal = await journal_service.reverse(
            note.posting_journal_entry_id,
            session=session,
            actor_user_id=actor_user_id,
            description=f"Reversal of credit note {note.credit_note_number}",
        )
        reversing_je_id = reversal.id
    note.state = CreditNoteState.CANCELLED
    await session.flush()
    await _emit(
        session,
        event_type=ar_events.TYPE_CREDIT_NOTE_CANCELLED,
        aggregate_id=note.id,
        payload={
            "credit_note_id": str(note.id),
            "credit_note_number": note.credit_note_number,
            "customer_id": str(note.customer_id),
            "reversing_journal_entry_id": (str(reversing_je_id) if reversing_je_id else None),
        },
        actor_user_id=actor_user_id,
    )
    return note


async def get(session: AsyncSession, credit_note_id: uuid.UUID) -> CreditNote:
    return await _load(session, credit_note_id)


async def list_credit_notes(
    session: AsyncSession,
    *,
    customer_id: uuid.UUID | None = None,
    invoice_id: uuid.UUID | None = None,
    state: str | None = None,
    limit: int = 50,
) -> list[CreditNote]:
    stmt = select(CreditNote)
    if customer_id is not None:
        stmt = stmt.where(CreditNote.customer_id == customer_id)
    if invoice_id is not None:
        stmt = stmt.where(CreditNote.invoice_id == invoice_id)
    if state is not None:
        try:
            stmt = stmt.where(CreditNote.state == CreditNoteState(state))
        except ValueError as exc:
            raise CreditNoteServiceError(f"invalid state filter: {state!r}") from exc
    stmt = stmt.order_by(CreditNote.created_at.desc()).limit(limit)
    return list((await session.execute(stmt)).scalars().all())


__all__ = [
    "CreditNoteNotFoundError",
    "CreditNoteServiceError",
    "InvalidCreditNoteAmountError",
    "InvalidCreditNoteStateError",
    "apply",
    "cancel",
    "create_draft",
    "get",
    "issue",
    "list_credit_notes",
    "update_draft",
]
