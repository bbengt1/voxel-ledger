"""Debit-notes service (Phase 7.4, #112).

Mirror of credit_notes but the opposite direction: a debit note
INCREASES what the customer owes on an already-issued invoice.
Issuing posts ``debit AR / credit Revenue``. Applying increases the
invoice's outstanding balance.

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
from app.models.credit_note import DebitNote, DebitNoteState
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


class DebitNoteServiceError(Exception):
    pass


class DebitNoteNotFoundError(DebitNoteServiceError):
    pass


class InvalidDebitNoteStateError(DebitNoteServiceError):
    pass


class InvalidDebitNoteAmountError(DebitNoteServiceError):
    pass


_QUANTUM = Decimal("0.000001")
_ZERO = Decimal("0")


def _q(value: Decimal | str | int | float) -> Decimal:
    if not isinstance(value, Decimal):
        value = Decimal(str(value))
    return value.quantize(_QUANTUM, rounding=ROUND_HALF_UP)


async def _load(session: AsyncSession, debit_note_id: uuid.UUID) -> DebitNote:
    row = (
        await session.execute(select(DebitNote).where(DebitNote.id == debit_note_id))
    ).scalar_one_or_none()
    if row is None:
        raise DebitNoteNotFoundError(str(debit_note_id))
    return row


async def _load_invoice(session: AsyncSession, invoice_id: uuid.UUID) -> Invoice:
    row = (
        await session.execute(select(Invoice).where(Invoice.id == invoice_id))
    ).scalar_one_or_none()
    if row is None:
        raise DebitNoteServiceError(f"invoice {invoice_id} not found")
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
            aggregate_type=ar_events.AGGREGATE_TYPE_DEBIT_NOTE,
            aggregate_id=aggregate_id,
            payload=payload,
            occurred_at=datetime.now(UTC),
            correlation_id=uuid.uuid4(),
            actor_user_id=actor_user_id,
        ),
        session=session,
    )


async def create_draft(
    session: AsyncSession,
    *,
    invoice_id: uuid.UUID,
    total_amount: Decimal | str | int | float,
    reason: str = "",
    notes: str | None = None,
    actor_user_id: uuid.UUID,
) -> DebitNote:
    invoice = await _load_invoice(session, invoice_id)
    amt = _q(total_amount)
    if amt <= _ZERO:
        raise InvalidDebitNoteAmountError("debit note total must be > 0")

    number = await ReferenceNumberService.allocate("DN", session=session)
    note = DebitNote(
        debit_note_number=number,
        customer_id=invoice.customer_id,
        invoice_id=invoice.id,
        reason=reason,
        total_amount=amt,
        state=DebitNoteState.DRAFT,
        notes=notes,
        created_by_user_id=actor_user_id,
    )
    session.add(note)
    await session.flush()
    await _emit(
        session,
        event_type=ar_events.TYPE_DEBIT_NOTE_CREATED,
        aggregate_id=note.id,
        payload={
            "debit_note_id": str(note.id),
            "debit_note_number": number,
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
    debit_note_id: uuid.UUID,
    patch: dict[str, Any],
    actor_user_id: uuid.UUID,
) -> DebitNote:
    note = await _load(session, debit_note_id)
    if note.state != DebitNoteState.DRAFT:
        raise InvalidDebitNoteStateError(f"debit note {note.debit_note_number} is not a draft")
    before: dict[str, Any] = {}
    after: dict[str, Any] = {}
    for field in ("reason", "notes", "total_amount"):
        if field not in patch:
            continue
        new = patch[field]
        if field == "total_amount":
            new = _q(new)
            if new <= _ZERO:
                raise InvalidDebitNoteAmountError("debit note total must be > 0")
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
        event_type=ar_events.TYPE_DEBIT_NOTE_UPDATED,
        aggregate_id=note.id,
        payload={
            "debit_note_id": str(note.id),
            "before": before,
            "after": after,
        },
        actor_user_id=actor_user_id,
    )
    return note


async def issue(
    session: AsyncSession,
    *,
    debit_note_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    revenue_account_id_override: uuid.UUID | None = None,
) -> DebitNote:
    note = await _load(session, debit_note_id)
    if note.state != DebitNoteState.DRAFT:
        raise InvalidDebitNoteStateError(f"debit note {note.debit_note_number} is not a draft")
    invoice = await _load_invoice(session, note.invoice_id)
    from app.models.customer import Customer

    customer = (
        await session.execute(select(Customer).where(Customer.id == note.customer_id))
    ).scalar_one()
    amt = _q(note.total_amount)

    # QBO replace-mode (epic #312, Phase 3c-2): QBO has no native customer
    # debit-memo, so push a JournalEntry — Dr A/R (with the Customer Entity,
    # required by QBO), Cr Revenue — via the sync outbox instead of the local GL.
    from app.services.quickbooks import outbox as qbo_outbox

    qbo_enabled = await qbo_outbox.is_enabled(session)
    posted_entry_id: uuid.UUID | None = None
    if qbo_enabled:
        await qbo_outbox.enqueue(
            session,
            kind="debit_note",
            local_id=note.id,
            payload={
                "lines": [
                    {
                        "role": "accounts_receivable",
                        "posting": "debit",
                        "amount": str(amt),
                        "entity": {"type": "Customer", "local_id": str(note.customer_id)},
                        "description": f"Debit note {note.debit_note_number}",
                    },
                    {"role": "revenue", "posting": "credit", "amount": str(amt)},
                ],
                "doc_number": note.debit_note_number,
                "private_note": f"Debit note {note.debit_note_number}",
            },
            op="post",
        )
    else:
        ar_account_id = await _resolve_invoice_ar_account(session, customer=customer)
        if revenue_account_id_override is not None:
            revenue_account_id = revenue_account_id_override
        else:
            revenue_account_id = await _resolve_invoice_revenue_account(session, customer=customer)
        lines = [
            journal_service.JournalLineInput(
                account_id=ar_account_id,
                debit=amt,
                credit=_ZERO,
                line_number=1,
                memo=f"Debit note {note.debit_note_number} (AR increase)",
            ),
            journal_service.JournalLineInput(
                account_id=revenue_account_id,
                debit=_ZERO,
                credit=amt,
                line_number=2,
                memo=f"Debit note {note.debit_note_number} (revenue)",
            ),
        ]
        entry = await journal_service.post(
            journal_service.JournalEntryInput(
                description=f"Debit note {note.debit_note_number}",
                posted_at=datetime.now(UTC),
                lines=lines,
            ),
            session=session,
            actor_user_id=actor_user_id,
            _internal_skip_approval_check=True,
        )
        assert isinstance(entry, JournalEntry)
        posted_entry_id = entry.id

    note.state = DebitNoteState.ISSUED
    note.posting_journal_entry_id = posted_entry_id
    await session.flush()
    await _emit(
        session,
        event_type=ar_events.TYPE_DEBIT_NOTE_ISSUED,
        aggregate_id=note.id,
        payload={
            "debit_note_id": str(note.id),
            "debit_note_number": note.debit_note_number,
            "customer_id": str(note.customer_id),
            "invoice_id": str(invoice.id),
            "total_amount": str(amt),
            "journal_entry_id": str(posted_entry_id) if posted_entry_id else None,
        },
        actor_user_id=actor_user_id,
    )
    return note


async def apply(
    session: AsyncSession,
    *,
    debit_note_id: uuid.UUID,
    actor_user_id: uuid.UUID,
) -> DebitNote:
    note = await _load(session, debit_note_id)
    if note.state != DebitNoteState.ISSUED:
        raise InvalidDebitNoteStateError(f"debit note {note.debit_note_number} is not issued")
    invoice = await _load_invoice(session, note.invoice_id)
    if invoice.state in (InvoiceState.DRAFT, InvoiceState.VOID):
        raise InvalidDebitNoteStateError(
            f"cannot apply debit note to invoice in state {invoice.state.value}"
        )
    amt = _q(note.total_amount)
    invoice.amount_outstanding = _q(invoice.amount_outstanding + amt)
    invoice.total_amount = _q(invoice.total_amount + amt)
    if invoice.state == InvoiceState.PAID:
        invoice.state = InvoiceState.PARTIALLY_PAID
    note.state = DebitNoteState.APPLIED
    await session.flush()
    await _emit(
        session,
        event_type=ar_events.TYPE_DEBIT_NOTE_APPLIED,
        aggregate_id=note.id,
        payload={
            "debit_note_id": str(note.id),
            "debit_note_number": note.debit_note_number,
            "customer_id": str(note.customer_id),
            "invoice_id": str(invoice.id),
            "amount_applied": str(amt),
        },
        actor_user_id=actor_user_id,
    )
    return note


async def cancel(
    session: AsyncSession,
    *,
    debit_note_id: uuid.UUID,
    actor_user_id: uuid.UUID,
) -> DebitNote:
    note = await _load(session, debit_note_id)
    if note.state == DebitNoteState.CANCELLED:
        return note
    if note.state == DebitNoteState.APPLIED:
        raise InvalidDebitNoteStateError(
            f"debit note {note.debit_note_number} is applied; cannot cancel"
        )
    reversing_je_id: uuid.UUID | None = None
    if note.state == DebitNoteState.ISSUED and note.posting_journal_entry_id is not None:
        reversal = await journal_service.reverse(
            note.posting_journal_entry_id,
            session=session,
            actor_user_id=actor_user_id,
            description=f"Reversal of debit note {note.debit_note_number}",
        )
        reversing_je_id = reversal.id
    elif note.state == DebitNoteState.ISSUED:
        from app.services.quickbooks import outbox as qbo_outbox

        if await qbo_outbox.is_enabled(session):
            await qbo_outbox.enqueue(
                session,
                kind="debit_note",
                local_id=note.id,
                payload={"debit_note_id": str(note.id)},
                op="reverse",
            )
    note.state = DebitNoteState.CANCELLED
    await session.flush()
    await _emit(
        session,
        event_type=ar_events.TYPE_DEBIT_NOTE_CANCELLED,
        aggregate_id=note.id,
        payload={
            "debit_note_id": str(note.id),
            "debit_note_number": note.debit_note_number,
            "customer_id": str(note.customer_id),
            "reversing_journal_entry_id": (str(reversing_je_id) if reversing_je_id else None),
        },
        actor_user_id=actor_user_id,
    )
    return note


async def get(session: AsyncSession, debit_note_id: uuid.UUID) -> DebitNote:
    return await _load(session, debit_note_id)


async def list_debit_notes(
    session: AsyncSession,
    *,
    customer_id: uuid.UUID | None = None,
    invoice_id: uuid.UUID | None = None,
    state: str | None = None,
    limit: int = 50,
) -> list[DebitNote]:
    stmt = select(DebitNote)
    if customer_id is not None:
        stmt = stmt.where(DebitNote.customer_id == customer_id)
    if invoice_id is not None:
        stmt = stmt.where(DebitNote.invoice_id == invoice_id)
    if state is not None:
        try:
            stmt = stmt.where(DebitNote.state == DebitNoteState(state))
        except ValueError as exc:
            raise DebitNoteServiceError(f"invalid state filter: {state!r}") from exc
    stmt = stmt.order_by(DebitNote.created_at.desc()).limit(limit)
    return list((await session.execute(stmt)).scalars().all())


__all__ = [
    "DebitNoteNotFoundError",
    "DebitNoteServiceError",
    "InvalidDebitNoteAmountError",
    "InvalidDebitNoteStateError",
    "apply",
    "cancel",
    "create_draft",
    "get",
    "issue",
    "list_debit_notes",
    "update_draft",
]
