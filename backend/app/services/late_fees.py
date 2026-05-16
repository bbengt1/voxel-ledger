"""Late-fees worker (Phase 7.6, #114).

Two worker entrypoints live here:

* :func:`mark_overdue_invoices` — runs every 6 hours
  (cron ``0 */6 * * *``). Sweeps ``due_at < now() AND state IN (issued,
  partially_paid)`` and flips the row to ``state=overdue``, emitting
  ``ar.InvoiceOverdue``. Idempotent: invoices already in ``overdue`` are
  skipped.

* :func:`apply_late_fees` — runs daily at 1 AM (cron ``0 1 * * *``).
  For each overdue invoice past ``due_at + apply_after_days``, looks up
  the most-specific active policy, computes the fee, and issues a
  ``debit_note`` (Phase 7.4) with ``reason="late_fee"``.

Idempotency is service-level: the worker scans prior
``ar.LateFeeApplied`` events for the invoice and refuses to re-emit
within ``compound_interval_days`` for ``compound_percent`` policies
(and at all for one-shot kinds).
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.events.types import ar as ar_events
from app.models.invoice import Invoice, InvoiceState
from app.models.late_fee_policy import LateFeeKind, LateFeePolicy
from app.schemas.events import EventCreate
from app.services import debit_notes as debit_notes_service
from app.services import event_store
from app.services import late_fee_policies as policy_service

log = logging.getLogger(__name__)


_QUANTUM = Decimal("0.01")
_ZERO = Decimal("0")


def _q(value: Decimal | str | int | float) -> Decimal:
    if not isinstance(value, Decimal):
        value = Decimal(str(value))
    return value.quantize(_QUANTUM, rounding=ROUND_HALF_UP)


@dataclass
class OverdueMarkResult:
    marked: int
    skipped: int


@dataclass
class LateFeeApplyResult:
    applied: int
    skipped: int
    # Retained for response-schema compatibility; always False now that Phase 7.4 is merged.
    deferred: bool
    fees_total: Decimal


# ---------------------------------------------------------------------------
# Overdue marker
# ---------------------------------------------------------------------------


async def mark_overdue_invoices(
    *,
    session: AsyncSession,
    now: datetime | None = None,
    actor_user_id: uuid.UUID | None = None,
) -> OverdueMarkResult:
    """Sweep past-due ``issued`` / ``partially_paid`` invoices.

    Atomic with respect to the caller's transaction — the caller is
    responsible for committing. Idempotent: a row already in
    ``overdue`` is skipped (the state guard means a second sweep is a
    no-op).
    """
    if now is None:
        now = datetime.now(UTC)
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)

    stmt = (
        select(Invoice)
        .where(Invoice.due_at.is_not(None))
        .where(Invoice.due_at < now)
        .where(Invoice.state.in_([InvoiceState.ISSUED, InvoiceState.PARTIALLY_PAID]))
    )
    rows = list((await session.execute(stmt)).scalars().all())

    marked = 0
    for invoice in rows:
        invoice.state = InvoiceState.OVERDUE
        marked += 1
        due_at = invoice.due_at
        if due_at is not None and due_at.tzinfo is None:
            due_at = due_at.replace(tzinfo=UTC)
        days_overdue = max(0, (now - due_at).days) if due_at else 0
        await _emit(
            session,
            event_type=ar_events.TYPE_INVOICE_OVERDUE,
            aggregate_id=invoice.id,
            payload={
                "invoice_id": str(invoice.id),
                "invoice_number": invoice.invoice_number,
                "customer_id": str(invoice.customer_id),
                "days_overdue": days_overdue,
                "total_amount": str(invoice.total_amount),
                "amount_outstanding": str(invoice.amount_outstanding),
            },
            actor_user_id=actor_user_id,
        )
    await session.flush()
    return OverdueMarkResult(marked=marked, skipped=0)


# ---------------------------------------------------------------------------
# Late fee application
# ---------------------------------------------------------------------------


def _compute_fee(
    policy: LateFeePolicy,
    *,
    outstanding: Decimal,
    days_overdue: int,
) -> Decimal:
    """Compute the fee for one invoice given the policy.

    * ``percent_of_outstanding``: ``outstanding * amount`` (one-shot).
    * ``flat``: ``amount`` (one-shot).
    * ``compound_percent``: ``outstanding * amount`` per
      ``compound_interval_days`` past the apply threshold. The caller
      governs how often this runs (daily), so we return the per-tick
      fee — the (invoice, day) idempotency keeps re-applies in check
      between intervals.
    """
    if policy.kind == LateFeeKind.FLAT:
        return _q(policy.amount)
    if policy.kind == LateFeeKind.PERCENT_OF_OUTSTANDING:
        return _q(outstanding * policy.amount)
    if policy.kind == LateFeeKind.COMPOUND_PERCENT:
        return _q(outstanding * policy.amount)
    raise ValueError(f"unknown late_fee_kind: {policy.kind!r}")


def _should_apply_today(
    *,
    policy: LateFeePolicy,
    days_overdue: int,
    last_applied: date | None,
    today: date,
) -> bool:
    """Decide if a fee should be applied today for this policy.

    * Must be past ``apply_after_days`` past due (with grace).
    * For ``compound_percent``: must be at least ``compound_interval_days``
      since the last application.
    * For one-shot kinds: only if never applied before.
    """
    threshold = policy.apply_after_days + policy.grace_period_days
    if days_overdue < threshold:
        return False

    if last_applied is None:
        return True

    if policy.kind == LateFeeKind.COMPOUND_PERCENT:
        return (today - last_applied).days >= policy.compound_interval_days

    # One-shot kinds: don't reapply if there's any prior late-fee debit note.
    return False


async def apply_late_fees(
    *,
    session: AsyncSession,
    now: datetime | None = None,
    actor_user_id: uuid.UUID | None = None,
) -> LateFeeApplyResult:
    """Daily worker entrypoint: apply late fees to overdue invoices.

    Returns a structured result. The caller commits the transaction.
    """
    if now is None:
        now = datetime.now(UTC)
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    today = now.date()

    stmt = select(Invoice).where(
        Invoice.state.in_([InvoiceState.OVERDUE, InvoiceState.PARTIALLY_PAID, InvoiceState.ISSUED])
    )
    rows = list((await session.execute(stmt)).scalars().all())

    applied = 0
    skipped = 0
    fees_total = _ZERO

    for invoice in rows:
        if invoice.due_at is None:
            skipped += 1
            continue
        due_at = invoice.due_at
        if due_at.tzinfo is None:
            due_at = due_at.replace(tzinfo=UTC)
        days_overdue = (now - due_at).days
        if days_overdue <= 0:
            skipped += 1
            continue
        outstanding = _q(invoice.amount_outstanding)
        if outstanding <= _ZERO:
            skipped += 1
            continue

        policy = await policy_service.resolve_for_customer(session, customer_id=invoice.customer_id)
        if policy is None:
            skipped += 1
            continue

        last_applied = await _last_late_fee_date(session, invoice_id=invoice.id)
        if not _should_apply_today(
            policy=policy,
            days_overdue=days_overdue,
            last_applied=last_applied,
            today=today,
        ):
            skipped += 1
            continue

        fee = _compute_fee(policy, outstanding=outstanding, days_overdue=days_overdue)
        if fee <= _ZERO:
            skipped += 1
            continue

        debit_note_id: uuid.UUID | None = None
        try:
            debit_note_id = await _create_and_issue_debit_note(
                session=session,
                invoice=invoice,
                fee=fee,
                policy=policy,
                actor_user_id=actor_user_id,
            )
        except Exception as exc:  # pragma: no cover - defensive
            log.warning(
                "late-fee debit note creation failed for invoice %s: %s",
                invoice.id,
                exc,
            )
            skipped += 1
            continue

        await _emit(
            session,
            event_type=ar_events.TYPE_LATE_FEE_APPLIED,
            aggregate_id=invoice.id,
            payload={
                "invoice_id": str(invoice.id),
                "invoice_number": invoice.invoice_number,
                "customer_id": str(invoice.customer_id),
                "policy_id": str(policy.id),
                "debit_note_id": str(debit_note_id) if debit_note_id else None,
                "amount": str(fee),
                "applied_at": now.isoformat(),
            },
            actor_user_id=actor_user_id,
            occurred_at=now,
        )
        applied += 1
        fees_total += fee

    await session.flush()
    return LateFeeApplyResult(
        applied=applied,
        skipped=skipped,
        deferred=False,
        fees_total=fees_total,
    )


async def _last_late_fee_date(
    session: AsyncSession,
    *,
    invoice_id: uuid.UUID,
) -> date | None:
    """Return the date of the most recent late-fee application for an invoice.

    Scans the ``ar.LateFeeApplied`` event log — the same source of
    truth that powers the audit trail. Used to enforce the compound
    interval and one-shot guards.
    """
    from app.models.event import Event

    stmt = (
        select(Event)
        .where(Event.type == ar_events.TYPE_LATE_FEE_APPLIED)
        .where(Event.aggregate_id == invoice_id)
        .order_by(Event.occurred_at.desc())
        .limit(1)
    )
    row = (await session.execute(stmt)).scalars().first()
    if row is None:
        return None
    occurred = row.occurred_at
    if occurred is None:
        return None
    if occurred.tzinfo is None:
        occurred = occurred.replace(tzinfo=UTC)
    return occurred.date()


async def _create_and_issue_debit_note(
    *,
    session: AsyncSession,
    invoice: Invoice,
    fee: Decimal,
    policy: LateFeePolicy,
    actor_user_id: uuid.UUID | None,
) -> uuid.UUID:
    """Create + issue a Phase 7.4 ``debit_note`` for a late-fee application.

    The ``debit_notes`` service requires a non-null actor for the
    ``created_by_user_id`` FK. When the worker is triggered by the
    daily cron (``actor_user_id=None``) we fall back to the invoice's
    creator so the audit trail still has a sensible owner.
    """
    effective_actor = actor_user_id or invoice.created_by_user_id
    draft = await debit_notes_service.create_draft(
        session,
        invoice_id=invoice.id,
        total_amount=fee,
        reason="late_fee",
        actor_user_id=effective_actor,
    )
    issued = await debit_notes_service.issue(
        session,
        debit_note_id=draft.id,
        actor_user_id=effective_actor,
    )
    return issued.id


async def _emit(
    session: AsyncSession,
    *,
    event_type: str,
    aggregate_id: uuid.UUID,
    payload: dict[str, Any],
    actor_user_id: uuid.UUID | None,
    occurred_at: datetime | None = None,
) -> None:
    await event_store.append(
        EventCreate(
            type=event_type,
            aggregate_type=ar_events.AGGREGATE_TYPE_INVOICE,
            aggregate_id=aggregate_id,
            payload=payload,
            occurred_at=occurred_at or datetime.now(UTC),
            correlation_id=uuid.uuid4(),
            actor_user_id=actor_user_id,
        ),
        session=session,
    )
