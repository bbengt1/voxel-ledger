"""Payments service (Phase 7.4, #112).

Records customer remittances and applies them to outstanding invoices.
Posting (debit Cash/Bank, credit AR) is done inside the SAME DB
transaction as the application rows + invoice state cascade — the
same-TX rule the Phase 6.3 sale-confirm and Phase 7.3 invoice-issue
flows established.

State machine
-------------
``record_payment`` lands a payment in ``pending``. ``apply_payment``
posts a JE, links it to invoices via ``payment_application`` rows,
optionally accrues residue to customer credit, then flips
``state -> applied``. ``unapply_payment`` reverses the JE and clears
the applications (bookkeeper-only). ``mark_bounced`` is unapply +
``state -> bounced``. ``cancel`` is only valid from ``pending``.

Excess flow
-----------
If the sum of ``applications`` is < ``payment.amount`` and the caller
opts in with ``apply_excess_to_credit=True``, the residue is written
as a ``customer_credit_transaction`` accrual row and emitted as a
``ar.CustomerCreditAccrued`` event — the projection picks it up and
rebuilds ``customer_credit_balance``. Without the opt-in the service
rejects the call so the operator must consciously decide what happens
to an overpayment.

JE shape for a multi-invoice apply
----------------------------------
One debit-bank line + N credit-AR lines (one per invoice). When the
invoices have different AR accounts (per-customer overrides), the
single JE still works — same debit total, same credit total, split
across N lines. The Phase 7.3 issue flow reuses one AR account per
invoice; if a future change introduces a third dimension, refactor
the apply routine accordingly.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.events.types import ar as ar_events
from app.models.customer import Customer
from app.models.customer_credit import CustomerCreditKind, CustomerCreditTransaction
from app.models.invoice import Invoice, InvoiceState
from app.models.journal_entry import JournalEntry
from app.models.payment import Payment, PaymentApplication, PaymentMethod, PaymentState
from app.schemas.events import EventCreate
from app.services import event_store
from app.services import journal_entries as journal_service
from app.services.invoices import MissingArPostingAccountError
from app.services.invoices import _resolve_ar_account as _resolve_invoice_ar_account
from app.services.reference_number import ReferenceNumberService
from app.services.settings.service import SettingsService

# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class PaymentsServiceError(Exception):
    """Base. Routers map to 400 unless noted."""


class PaymentNotFoundError(PaymentsServiceError):
    """Mapped to 404."""


class CustomerNotFoundForPaymentError(PaymentsServiceError):
    pass


class InvalidPaymentStateError(PaymentsServiceError):
    """Illegal transition or write-while-not-pending."""


class InvalidPaymentAmountError(PaymentsServiceError):
    pass


class InvoiceNotFoundForApplicationError(PaymentsServiceError):
    pass


class OverApplicationError(PaymentsServiceError):
    """Applied amount exceeds invoice outstanding or payment amount."""


class ExcessNotPermittedError(PaymentsServiceError):
    """Excess present but caller didn't opt in to credit accrual."""


# ---------------------------------------------------------------------------
# Decimal helpers
# ---------------------------------------------------------------------------

_QUANTUM = Decimal("0.000001")
_ZERO = Decimal("0")


def _q(value: Decimal | str | int | float) -> Decimal:
    if not isinstance(value, Decimal):
        value = Decimal(str(value))
    return value.quantize(_QUANTUM, rounding=ROUND_HALF_UP)


def _coerce_method(value: str | PaymentMethod) -> PaymentMethod:
    if isinstance(value, PaymentMethod):
        return value
    try:
        return PaymentMethod(value)
    except ValueError as exc:
        raise PaymentsServiceError(f"invalid payment method: {value!r}") from exc


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------


async def _load_payment(session: AsyncSession, payment_id: uuid.UUID) -> Payment:
    stmt = (
        select(Payment).where(Payment.id == payment_id).options(selectinload(Payment.applications))
    )
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise PaymentNotFoundError(str(payment_id))
    return row


async def _load_customer(session: AsyncSession, customer_id: uuid.UUID) -> Customer:
    row = (
        await session.execute(select(Customer).where(Customer.id == customer_id))
    ).scalar_one_or_none()
    if row is None:
        raise CustomerNotFoundForPaymentError(str(customer_id))
    return row


async def _load_invoice(session: AsyncSession, invoice_id: uuid.UUID) -> Invoice:
    row = (
        await session.execute(select(Invoice).where(Invoice.id == invoice_id))
    ).scalar_one_or_none()
    if row is None:
        raise InvoiceNotFoundForApplicationError(str(invoice_id))
    return row


# ---------------------------------------------------------------------------
# Event emission helper
# ---------------------------------------------------------------------------


async def _emit(
    session: AsyncSession,
    *,
    event_type: str,
    aggregate_id: uuid.UUID,
    payload: dict[str, Any],
    actor_user_id: uuid.UUID | None,
    aggregate_type: str = ar_events.AGGREGATE_TYPE_PAYMENT,
) -> None:
    await event_store.append(
        EventCreate(
            type=event_type,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            payload=payload,
            occurred_at=datetime.now(UTC),
            correlation_id=uuid.uuid4(),
            actor_user_id=actor_user_id,
        ),
        session=session,
    )


# ---------------------------------------------------------------------------
# Bank-account resolution
# ---------------------------------------------------------------------------


async def _resolve_undeposited_account(session: AsyncSession) -> uuid.UUID:
    """Resolve the undeposited-funds clearing account (Parity #235).

    Set on the ``ar.undeposited_funds_account_id`` setting. Raises
    ``MissingArPostingAccountError`` when unset — the caller asked
    for the undeposited workflow and we can't service it.
    """
    raw = await SettingsService.get(
        "ar.undeposited_funds_account_id", session=session
    )
    if raw is None:
        raise MissingArPostingAccountError(
            "set 'ar.undeposited_funds_account_id' or omit "
            "deposit_to_undeposited (needed to debit the clearing "
            "account for a payment headed to a deposit slip)"
        )
    return raw if isinstance(raw, uuid.UUID) else uuid.UUID(str(raw))


async def _resolve_bank_account(
    session: AsyncSession,
    *,
    method: PaymentMethod,
    deposit_to_undeposited: bool = False,
) -> uuid.UUID:
    """Resolve the bank/cash account credited at posting.

    When ``deposit_to_undeposited`` is True the payment debits the
    configured undeposited-funds clearing account (Parity #235).
    Otherwise: ``ar.payment_method_to_account`` (JSON map) takes
    precedence; falls through to ``ar.default_bank_account_id``.
    Raises ``MissingArPostingAccountError`` if neither resolves.
    """
    if deposit_to_undeposited:
        return await _resolve_undeposited_account(session)
    mapping = await SettingsService.get("ar.payment_method_to_account", session=session)
    if isinstance(mapping, dict):
        raw = mapping.get(method.value)
        if raw:
            if isinstance(raw, uuid.UUID):
                return raw
            try:
                return uuid.UUID(str(raw))
            except ValueError as exc:
                raise MissingArPostingAccountError(
                    f"ar.payment_method_to_account[{method.value!r}] is not a valid UUID"
                ) from exc

    default = await SettingsService.get("ar.default_bank_account_id", session=session)
    if default is not None:
        if isinstance(default, uuid.UUID):
            return default
        return uuid.UUID(str(default))

    raise MissingArPostingAccountError(
        "configure default AR posting accounts: neither "
        f"ar.payment_method_to_account[{method.value!r}] nor "
        "ar.default_bank_account_id are set (needed to debit the bank "
        "account for a payment)"
    )


# ---------------------------------------------------------------------------
# record_payment
# ---------------------------------------------------------------------------


async def record_payment(
    session: AsyncSession,
    *,
    customer_id: uuid.UUID,
    amount: Decimal | str | int | float,
    method: str | PaymentMethod,
    reference: str | None = None,
    received_at: datetime | None = None,
    notes: str | None = None,
    actor_user_id: uuid.UUID,
    deposit_to_undeposited: bool = False,
) -> Payment:
    """Record a customer remittance in ``state=pending``. No GL effect.

    When ``deposit_to_undeposited`` is True the eventual apply-payment
    JE will debit ``ar.undeposited_funds_account_id`` instead of the
    bank account (Parity #235). A subsequent ``deposit_slip`` moves
    the consolidated balance to the bank account in a single JE.
    """
    customer = await _load_customer(session, customer_id)
    amt = _q(amount)
    if amt <= _ZERO:
        raise InvalidPaymentAmountError("payment amount must be > 0")
    method_enum = _coerce_method(method)

    payment_number = await ReferenceNumberService.allocate("PMT", session=session)
    received = received_at or datetime.now(UTC)

    payment = Payment(
        payment_number=payment_number,
        customer_id=customer.id,
        received_at=received,
        method=method_enum,
        reference=reference,
        amount=amt,
        state=PaymentState.PENDING,
        notes=notes,
        created_by_user_id=actor_user_id,
        deposit_to_undeposited=deposit_to_undeposited,
    )
    session.add(payment)
    await session.flush()

    await _emit(
        session,
        event_type=ar_events.TYPE_PAYMENT_RECORDED,
        aggregate_id=payment.id,
        payload={
            "payment_id": str(payment.id),
            "payment_number": payment_number,
            "customer_id": str(customer.id),
            "method": method_enum.value,
            "reference": reference,
            "amount": str(amt),
            "received_at": received.isoformat(),
            "state": payment.state.value,
            "notes": notes,
        },
        actor_user_id=actor_user_id,
    )
    return await _load_payment(session, payment.id)


# ---------------------------------------------------------------------------
# Invoice state cascade
# ---------------------------------------------------------------------------


def _cascade_state(invoice: Invoice) -> None:
    """Recompute state from amount_paid / amount_outstanding.

    Only moves invoices that are in ``issued`` / ``partially_paid`` /
    ``overdue`` — never overrides ``void``/``paid`` (paid is the final
    state we're aiming at; once there, further mutations are illegal
    upstream).
    """
    outstanding = _q(invoice.amount_outstanding)
    paid = _q(invoice.amount_paid)
    if invoice.state == InvoiceState.PAID:
        return
    if invoice.state == InvoiceState.VOID:
        return
    if outstanding <= _ZERO:
        invoice.state = InvoiceState.PAID
        return
    if paid > _ZERO:
        invoice.state = InvoiceState.PARTIALLY_PAID


# ---------------------------------------------------------------------------
# apply_payment
# ---------------------------------------------------------------------------


async def apply_payment(
    session: AsyncSession,
    *,
    payment_id: uuid.UUID,
    applications: list[tuple[uuid.UUID, Decimal | str]],
    apply_excess_to_credit: bool = False,
    actor_user_id: uuid.UUID,
) -> Payment:
    """Apply a recorded payment to one or more invoices.

    Validates per-line and aggregate caps, updates each invoice's
    ``amount_paid`` / ``amount_outstanding`` / state, posts the bank /
    AR journal entry, optionally accrues residue to customer credit,
    and flips the payment to ``state=applied``.
    """
    payment = await _load_payment(session, payment_id)
    if payment.state != PaymentState.PENDING:
        raise InvalidPaymentStateError(
            f"payment {payment.payment_number} is in state {payment.state.value}; "
            "only pending payments can be applied"
        )

    customer = await _load_customer(session, payment.customer_id)
    total_amount = _q(payment.amount)

    normalized: list[tuple[Invoice, Decimal]] = []
    running_total = _ZERO
    for invoice_id, raw_amt in applications:
        amt = _q(raw_amt)
        if amt <= _ZERO:
            raise InvalidPaymentAmountError(
                f"application amount must be > 0 (invoice {invoice_id})"
            )
        invoice = await _load_invoice(session, invoice_id)
        if invoice.customer_id != customer.id:
            raise PaymentsServiceError(
                f"invoice {invoice.invoice_number} belongs to a different customer"
            )
        if invoice.state in (InvoiceState.DRAFT, InvoiceState.VOID, InvoiceState.PAID):
            raise InvalidPaymentStateError(
                f"cannot apply to invoice {invoice.invoice_number} in state {invoice.state.value}"
            )
        outstanding = _q(invoice.amount_outstanding)
        if amt > outstanding:
            raise OverApplicationError(
                f"application of {amt} exceeds invoice {invoice.invoice_number} "
                f"outstanding {outstanding}"
            )
        running_total += amt
        normalized.append((invoice, amt))

    if running_total > total_amount:
        raise OverApplicationError(
            f"total applications {running_total} exceed payment amount {total_amount}"
        )
    excess = _q(total_amount - running_total)
    if excess > _ZERO and not apply_excess_to_credit:
        raise ExcessNotPermittedError(
            f"applications sum to {running_total} but payment is {total_amount}; "
            "pass apply_excess_to_credit=True to accrue the difference "
            "to the customer credit balance"
        )

    # Apply rows + invoice updates
    application_payload: list[dict[str, Any]] = []
    bank_account_id = await _resolve_bank_account(
        session,
        method=payment.method,
        deposit_to_undeposited=bool(payment.deposit_to_undeposited),
    )

    # Build JE lines. Single debit-bank line for full payment amount;
    # one credit-AR line per applied invoice (different AR accounts
    # supported via per-customer override). Excess (if any) ends up
    # credited to the AR for the customer too — but only the applied
    # slice reduces the invoice. Conceptually the bank line equals
    # applied + excess; the credit is then split between
    # invoice-AR lines and a customer-credit-clearing line. To keep
    # bookkeeping simple we credit AR for the *applied* portion and
    # credit AR for the customer's credit excess as well (the credit
    # balance projection tracks the "we owe customer X" side
    # separately). Net effect: bank +total, AR -total.
    lines_in: list[journal_service.JournalLineInput] = []
    line_no = 1
    lines_in.append(
        journal_service.JournalLineInput(
            account_id=bank_account_id,
            debit=total_amount,
            credit=_ZERO,
            line_number=line_no,
            memo=f"Payment {payment.payment_number} ({payment.method.value})",
        )
    )

    for invoice, amt in normalized:
        line_no += 1
        invoice.amount_paid = _q(invoice.amount_paid + amt)
        invoice.amount_outstanding = _q(invoice.amount_outstanding - amt)
        _cascade_state(invoice)

        ar_account_id = await _resolve_invoice_ar_account(session, customer=customer)
        lines_in.append(
            journal_service.JournalLineInput(
                account_id=ar_account_id,
                debit=_ZERO,
                credit=amt,
                line_number=line_no,
                memo=f"Apply {payment.payment_number} to {invoice.invoice_number}",
            )
        )
        application = PaymentApplication(
            payment_id=payment.id,
            invoice_id=invoice.id,
            amount=amt,
        )
        session.add(application)
        application_payload.append(
            {
                "invoice_id": str(invoice.id),
                "invoice_number": invoice.invoice_number,
                "amount": str(amt),
            }
        )

    # If there's excess, credit AR (for the customer's chain default).
    # The customer credit accrual is the journal-entry-independent
    # bookkeeping; the GL credit balances the bank debit. The credit
    # balance projection picks up CustomerCreditAccrued separately.
    if excess > _ZERO:
        line_no += 1
        ar_account_id = await _resolve_invoice_ar_account(session, customer=customer)
        lines_in.append(
            journal_service.JournalLineInput(
                account_id=ar_account_id,
                debit=_ZERO,
                credit=excess,
                line_number=line_no,
                memo=f"{payment.payment_number} excess -> customer credit",
            )
        )

    entry = await journal_service.post(
        journal_service.JournalEntryInput(
            description=f"Payment {payment.payment_number}: apply",
            posted_at=datetime.now(UTC),
            lines=lines_in,
        ),
        session=session,
        actor_user_id=actor_user_id,
        _internal_skip_approval_check=True,
    )
    assert isinstance(entry, JournalEntry)
    payment.posting_journal_entry_id = entry.id
    payment.state = PaymentState.APPLIED
    await session.flush()

    if excess > _ZERO:
        tx = CustomerCreditTransaction(
            customer_id=customer.id,
            kind=CustomerCreditKind.ACCRUAL,
            amount=excess,
            source_payment_id=payment.id,
            notes=f"Excess from {payment.payment_number}",
        )
        session.add(tx)
        await session.flush()
        await _emit(
            session,
            event_type=ar_events.TYPE_CUSTOMER_CREDIT_ACCRUED,
            aggregate_id=customer.id,
            payload={
                "customer_id": str(customer.id),
                "transaction_id": str(tx.id),
                "amount": str(excess),
                "source_payment_id": str(payment.id),
                "notes": tx.notes,
            },
            actor_user_id=actor_user_id,
            aggregate_type=ar_events.AGGREGATE_TYPE_CUSTOMER_CREDIT,
        )

    await _emit(
        session,
        event_type=ar_events.TYPE_PAYMENT_APPLIED,
        aggregate_id=payment.id,
        payload={
            "payment_id": str(payment.id),
            "payment_number": payment.payment_number,
            "customer_id": str(customer.id),
            "applications": application_payload,
            "total_applied": str(running_total),
            "excess_to_credit": str(excess),
        },
        actor_user_id=actor_user_id,
    )
    await _emit(
        session,
        event_type=ar_events.TYPE_PAYMENT_POSTED,
        aggregate_id=payment.id,
        payload={
            "payment_id": str(payment.id),
            "payment_number": payment.payment_number,
            "customer_id": str(customer.id),
            "amount": str(total_amount),
            "method": payment.method.value,
            "journal_entry_id": str(entry.id),
        },
        actor_user_id=actor_user_id,
    )
    return await _load_payment(session, payment.id)


# ---------------------------------------------------------------------------
# unapply_payment
# ---------------------------------------------------------------------------


async def unapply_payment(
    session: AsyncSession,
    *,
    payment_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    new_state: PaymentState = PaymentState.PENDING,
) -> Payment:
    """Reverse the JE and clear payment_application rows.

    Restores each touched invoice's outstanding balance and reverses the
    state cascade. The payment's own state is moved to ``new_state``
    (default ``pending``; ``mark_bounced`` calls with ``bounced``).
    """
    payment = await _load_payment(session, payment_id)
    if payment.state != PaymentState.APPLIED:
        raise InvalidPaymentStateError(
            f"payment {payment.payment_number} is in state {payment.state.value}; "
            "only applied payments can be unapplied"
        )

    reversing_je_id: uuid.UUID | None = None
    original_je_id = payment.posting_journal_entry_id
    if original_je_id is not None:
        reversal = await journal_service.reverse(
            original_je_id,
            session=session,
            actor_user_id=actor_user_id,
            description=f"Reversal of payment {payment.payment_number}",
        )
        reversing_je_id = reversal.id

    # Restore invoice balances + state
    for app_row in list(payment.applications):
        invoice = await _load_invoice(session, app_row.invoice_id)
        amt = _q(app_row.amount)
        invoice.amount_paid = _q(invoice.amount_paid - amt)
        invoice.amount_outstanding = _q(invoice.amount_outstanding + amt)
        if invoice.amount_paid <= _ZERO and invoice.state in (
            InvoiceState.PARTIALLY_PAID,
            InvoiceState.PAID,
        ):
            invoice.state = InvoiceState.ISSUED
        elif invoice.state == InvoiceState.PAID and invoice.amount_outstanding > _ZERO:
            invoice.state = InvoiceState.PARTIALLY_PAID
        await session.delete(app_row)

    # If a customer-credit accrual rode along with this payment, void
    # it by appending a CustomerCreditApplied event referencing the
    # accrual (mirroring application semantics — net-zero balance).
    accrual = (
        (
            await session.execute(
                select(CustomerCreditTransaction).where(
                    CustomerCreditTransaction.source_payment_id == payment.id,
                    CustomerCreditTransaction.kind == CustomerCreditKind.ACCRUAL,
                )
            )
        )
        .scalars()
        .all()
    )
    for tx in accrual:
        reversal_tx = CustomerCreditTransaction(
            customer_id=tx.customer_id,
            kind=CustomerCreditKind.APPLICATION,
            amount=tx.amount,
            source_payment_id=payment.id,
            notes=f"Unapply reversal for {payment.payment_number}",
        )
        session.add(reversal_tx)
        await session.flush()
        await _emit(
            session,
            event_type=ar_events.TYPE_CUSTOMER_CREDIT_APPLIED,
            aggregate_id=tx.customer_id,
            payload={
                "customer_id": str(tx.customer_id),
                "transaction_id": str(reversal_tx.id),
                "amount": str(tx.amount),
                "notes": reversal_tx.notes,
            },
            actor_user_id=actor_user_id,
            aggregate_type=ar_events.AGGREGATE_TYPE_CUSTOMER_CREDIT,
        )

    payment.state = new_state
    payment.posting_journal_entry_id = None
    await session.flush()

    await _emit(
        session,
        event_type=ar_events.TYPE_PAYMENT_UNAPPLIED,
        aggregate_id=payment.id,
        payload={
            "payment_id": str(payment.id),
            "payment_number": payment.payment_number,
            "customer_id": str(payment.customer_id),
            "reversing_journal_entry_id": (str(reversing_je_id) if reversing_je_id else None),
            "original_journal_entry_id": (str(original_je_id) if original_je_id else None),
        },
        actor_user_id=actor_user_id,
    )
    return await _load_payment(session, payment.id)


async def mark_bounced(
    session: AsyncSession,
    *,
    payment_id: uuid.UUID,
    actor_user_id: uuid.UUID,
) -> Payment:
    """Unapply + state -> bounced. Bookkeeper-only at the router."""
    payment = await unapply_payment(
        session,
        payment_id=payment_id,
        actor_user_id=actor_user_id,
        new_state=PaymentState.BOUNCED,
    )
    await _emit(
        session,
        event_type=ar_events.TYPE_PAYMENT_BOUNCED,
        aggregate_id=payment.id,
        payload={
            "payment_id": str(payment.id),
            "payment_number": payment.payment_number,
            "customer_id": str(payment.customer_id),
        },
        actor_user_id=actor_user_id,
    )
    return payment


async def cancel(
    session: AsyncSession,
    *,
    payment_id: uuid.UUID,
    actor_user_id: uuid.UUID,
) -> Payment:
    payment = await _load_payment(session, payment_id)
    if payment.state != PaymentState.PENDING:
        raise InvalidPaymentStateError(
            f"payment {payment.payment_number} cannot be cancelled from state {payment.state.value}"
        )
    payment.state = PaymentState.CANCELLED
    await session.flush()
    await _emit(
        session,
        event_type=ar_events.TYPE_PAYMENT_CANCELLED,
        aggregate_id=payment.id,
        payload={
            "payment_id": str(payment.id),
            "payment_number": payment.payment_number,
            "customer_id": str(payment.customer_id),
        },
        actor_user_id=actor_user_id,
    )
    return await _load_payment(session, payment.id)


# ---------------------------------------------------------------------------
# Read APIs
# ---------------------------------------------------------------------------


async def get(session: AsyncSession, payment_id: uuid.UUID) -> Payment:
    return await _load_payment(session, payment_id)


async def list_payments(
    session: AsyncSession,
    *,
    customer_id: uuid.UUID | None = None,
    state: str | None = None,
    limit: int = 50,
) -> list[Payment]:
    stmt = select(Payment).options(selectinload(Payment.applications))
    if customer_id is not None:
        stmt = stmt.where(Payment.customer_id == customer_id)
    if state is not None:
        try:
            stmt = stmt.where(Payment.state == PaymentState(state))
        except ValueError as exc:
            raise PaymentsServiceError(f"invalid state filter: {state!r}") from exc
    stmt = stmt.order_by(Payment.created_at.desc()).limit(limit)
    return list((await session.execute(stmt)).scalars().all())


__all__ = [
    "CustomerNotFoundForPaymentError",
    "ExcessNotPermittedError",
    "InvalidPaymentAmountError",
    "InvalidPaymentStateError",
    "InvoiceNotFoundForApplicationError",
    "OverApplicationError",
    "PaymentNotFoundError",
    "PaymentsServiceError",
    "apply_payment",
    "cancel",
    "get",
    "list_payments",
    "mark_bounced",
    "record_payment",
    "unapply_payment",
]
