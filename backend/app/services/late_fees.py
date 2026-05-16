"""Late-fee policies + overdue-marker + late-fee applicator (Phase 7.6, #114).

Two worker-driven flows live here:

* :func:`mark_overdue` — scans ``invoice`` rows with ``due_at < now()`` and
  ``state IN (issued, partially_paid)`` and flips them to
  :data:`InvoiceState.OVERDUE` while emitting ``ar.InvoiceOverdue``. The
  state flip alone is idempotent: re-running on the same day is a no-op
  because already-overdue invoices fall out of the filter.

* :func:`apply_late_fees` — for each OVERDUE invoice past
  ``due_at + grace_period_days``, resolves the most-specific active
  :class:`LateFeePolicy` (customer-specific beats global) and (when the
  compound-interval gate allows) creates + issues + applies a debit note
  with ``reason="late_fee"``. Idempotency is anchored on the invoice's
  ``last_late_fee_applied_at`` column:

    - ``percent_of_outstanding`` and ``flat`` apply ONCE per invoice.
      ``last_late_fee_applied_at IS NOT NULL`` skips re-application.
    - ``compound_percent`` re-applies every ``compound_interval_days``.
      ``now() - last_late_fee_applied_at >= compound_interval_days`` is
      the gate.

  The debit-note credit account uses the operator-configured
  ``ar.default_late_fee_income_account_id`` if set, otherwise falls
  through to the standard ``ar.default_revenue_account_id`` resolution
  inside :func:`app.services.debit_notes.issue`.

Plus operator CRUD on :class:`LateFeePolicy` and the
``apply_late_fees_now`` operator-triggered entrypoint exposed via the
``/late-fee-policies/apply-now`` route.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
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
from app.services.settings.service import SettingsService

log = logging.getLogger(__name__)


class LateFeesServiceError(Exception):
    pass


class LateFeePolicyNotFoundError(LateFeesServiceError):
    pass


class InvalidLateFeePolicyError(LateFeesServiceError):
    pass


_QUANTUM = Decimal("0.01")
_ZERO = Decimal("0")


def _q(value: Decimal | str | int | float) -> Decimal:
    if not isinstance(value, Decimal):
        value = Decimal(str(value))
    return value.quantize(_QUANTUM, rounding=ROUND_HALF_UP)


# ---------------------------------------------------------------------------
# Event helper
# ---------------------------------------------------------------------------


async def _emit(
    session: AsyncSession,
    *,
    event_type: str,
    aggregate_type: str,
    aggregate_id: uuid.UUID,
    payload: dict[str, Any],
    actor_user_id: uuid.UUID | None,
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
# Policy CRUD
# ---------------------------------------------------------------------------


async def create_policy(
    session: AsyncSession,
    *,
    kind: LateFeeKind | str,
    amount: Decimal | str | int | float,
    customer_id: uuid.UUID | None = None,
    grace_period_days: int = 0,
    apply_after_days: int = 30,
    compound_interval_days: int = 30,
    is_active: bool = True,
    notes: str | None = None,
    actor_user_id: uuid.UUID | None,
) -> LateFeePolicy:
    try:
        kind_value = LateFeeKind(kind) if not isinstance(kind, LateFeeKind) else kind
    except ValueError as exc:
        raise InvalidLateFeePolicyError(f"invalid late fee kind: {kind!r}") from exc

    amount_dec = Decimal(str(amount))
    if amount_dec < _ZERO:
        raise InvalidLateFeePolicyError("amount must be >= 0")
    if grace_period_days < 0:
        raise InvalidLateFeePolicyError("grace_period_days must be >= 0")
    if apply_after_days < 0:
        raise InvalidLateFeePolicyError("apply_after_days must be >= 0")
    if compound_interval_days < 1:
        raise InvalidLateFeePolicyError("compound_interval_days must be >= 1")

    if is_active:
        existing = await _find_active_for_customer(session, customer_id=customer_id)
        if existing is not None:
            scope = (
                f"customer {customer_id}" if customer_id is not None else "the global scope"
            )
            raise InvalidLateFeePolicyError(
                f"an active late-fee policy already exists for {scope} "
                f"(policy {existing.id}); deactivate it first"
            )

    policy = LateFeePolicy(
        customer_id=customer_id,
        kind=kind_value,
        amount=amount_dec,
        grace_period_days=grace_period_days,
        apply_after_days=apply_after_days,
        compound_interval_days=compound_interval_days,
        is_active=is_active,
        notes=notes,
        created_by_user_id=actor_user_id,
    )
    session.add(policy)
    await session.flush()
    await _emit(
        session,
        event_type=ar_events.TYPE_LATE_FEE_POLICY_CREATED,
        aggregate_type=ar_events.AGGREGATE_TYPE_LATE_FEE_POLICY,
        aggregate_id=policy.id,
        payload={
            "policy_id": str(policy.id),
            "customer_id": str(customer_id) if customer_id else None,
            "kind": kind_value.value,
            "amount": str(amount_dec),
            "grace_period_days": grace_period_days,
            "apply_after_days": apply_after_days,
            "compound_interval_days": compound_interval_days,
            "is_active": is_active,
            "notes": notes,
        },
        actor_user_id=actor_user_id,
    )
    return policy


async def update_policy(
    session: AsyncSession,
    *,
    policy_id: uuid.UUID,
    patch: dict[str, Any],
    actor_user_id: uuid.UUID | None,
) -> LateFeePolicy:
    policy = await _load_policy(session, policy_id)
    before: dict[str, Any] = {}
    after: dict[str, Any] = {}
    mutable = {
        "kind",
        "amount",
        "grace_period_days",
        "apply_after_days",
        "compound_interval_days",
        "is_active",
        "notes",
    }
    for field, new in patch.items():
        if field not in mutable:
            raise InvalidLateFeePolicyError(f"field not mutable: {field!r}")
        if field == "kind":
            try:
                new = LateFeeKind(new) if not isinstance(new, LateFeeKind) else new
            except ValueError as exc:
                raise InvalidLateFeePolicyError(f"invalid late fee kind: {new!r}") from exc
        if field == "amount":
            new = Decimal(str(new))
            if new < _ZERO:
                raise InvalidLateFeePolicyError("amount must be >= 0")
        if field in {"grace_period_days", "apply_after_days"} and new < 0:
            raise InvalidLateFeePolicyError(f"{field} must be >= 0")
        if field == "compound_interval_days" and new < 1:
            raise InvalidLateFeePolicyError("compound_interval_days must be >= 1")
        current = getattr(policy, field)
        if current == new:
            continue
        before[field] = (
            current.value if isinstance(current, LateFeeKind)
            else str(current) if isinstance(current, Decimal)
            else current
        )
        after[field] = (
            new.value if isinstance(new, LateFeeKind)
            else str(new) if isinstance(new, Decimal)
            else new
        )
        setattr(policy, field, new)
    if not before:
        return policy
    await session.flush()
    await _emit(
        session,
        event_type=ar_events.TYPE_LATE_FEE_POLICY_UPDATED,
        aggregate_type=ar_events.AGGREGATE_TYPE_LATE_FEE_POLICY,
        aggregate_id=policy.id,
        payload={
            "policy_id": str(policy.id),
            "before": before,
            "after": after,
        },
        actor_user_id=actor_user_id,
    )
    return policy


async def deactivate_policy(
    session: AsyncSession,
    *,
    policy_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
) -> LateFeePolicy:
    policy = await _load_policy(session, policy_id)
    if not policy.is_active:
        return policy
    policy.is_active = False
    await session.flush()
    await _emit(
        session,
        event_type=ar_events.TYPE_LATE_FEE_POLICY_DEACTIVATED,
        aggregate_type=ar_events.AGGREGATE_TYPE_LATE_FEE_POLICY,
        aggregate_id=policy.id,
        payload={
            "policy_id": str(policy.id),
            "customer_id": str(policy.customer_id) if policy.customer_id else None,
        },
        actor_user_id=actor_user_id,
    )
    return policy


async def get_policy(session: AsyncSession, policy_id: uuid.UUID) -> LateFeePolicy:
    return await _load_policy(session, policy_id)


async def list_policies(
    session: AsyncSession,
    *,
    customer_id: uuid.UUID | None = None,
    include_inactive: bool = True,
    limit: int = 100,
) -> list[LateFeePolicy]:
    stmt = select(LateFeePolicy)
    if customer_id is not None:
        stmt = stmt.where(LateFeePolicy.customer_id == customer_id)
    if not include_inactive:
        stmt = stmt.where(LateFeePolicy.is_active.is_(True))
    stmt = stmt.order_by(LateFeePolicy.created_at.desc()).limit(limit)
    return list((await session.execute(stmt)).scalars().all())


async def _load_policy(session: AsyncSession, policy_id: uuid.UUID) -> LateFeePolicy:
    row = (
        await session.execute(select(LateFeePolicy).where(LateFeePolicy.id == policy_id))
    ).scalar_one_or_none()
    if row is None:
        raise LateFeePolicyNotFoundError(str(policy_id))
    return row


async def _find_active_for_customer(
    session: AsyncSession, *, customer_id: uuid.UUID | None
) -> LateFeePolicy | None:
    stmt = select(LateFeePolicy).where(LateFeePolicy.is_active.is_(True))
    if customer_id is None:
        stmt = stmt.where(LateFeePolicy.customer_id.is_(None))
    else:
        stmt = stmt.where(LateFeePolicy.customer_id == customer_id)
    return (await session.execute(stmt)).scalars().first()


async def _resolve_policy_for_customer(
    session: AsyncSession, *, customer_id: uuid.UUID
) -> LateFeePolicy | None:
    """Return per-customer active policy if any, else the active global one."""
    per_customer = await _find_active_for_customer(session, customer_id=customer_id)
    if per_customer is not None:
        return per_customer
    return await _find_active_for_customer(session, customer_id=None)


# ---------------------------------------------------------------------------
# Overdue marker
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class OverdueMarkResult:
    invoice_ids: list[uuid.UUID]


async def mark_overdue(
    session: AsyncSession,
    *,
    now: datetime | None = None,
    actor_user_id: uuid.UUID | None = None,
) -> OverdueMarkResult:
    """Flip every newly-overdue invoice and emit ``ar.InvoiceOverdue``."""
    now = now or datetime.now(UTC)
    stmt = (
        select(Invoice)
        .where(Invoice.due_at.is_not(None))
        .where(Invoice.due_at < now)
        .where(Invoice.state.in_((InvoiceState.ISSUED, InvoiceState.PARTIALLY_PAID)))
    )
    rows = list((await session.execute(stmt)).scalars().all())
    marked: list[uuid.UUID] = []
    for invoice in rows:
        days_overdue = (
            max((now - _as_utc(invoice.due_at)).days, 0) if invoice.due_at else 0
        )
        invoice.state = InvoiceState.OVERDUE
        await session.flush()
        await _emit(
            session,
            event_type=ar_events.TYPE_INVOICE_OVERDUE,
            aggregate_type=ar_events.AGGREGATE_TYPE_INVOICE,
            aggregate_id=invoice.id,
            payload={
                "invoice_id": str(invoice.id),
                "invoice_number": invoice.invoice_number,
                "customer_id": str(invoice.customer_id),
                "due_at": invoice.due_at.isoformat() if invoice.due_at else "",
                "days_overdue": days_overdue,
                "amount_outstanding": str(invoice.amount_outstanding),
            },
            actor_user_id=actor_user_id,
        )
        marked.append(invoice.id)
    return OverdueMarkResult(invoice_ids=marked)


# ---------------------------------------------------------------------------
# Late-fee applicator
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LateFeeApplicationResult:
    invoice_id: uuid.UUID
    policy_id: uuid.UUID
    debit_note_id: uuid.UUID
    amount: Decimal


def _compute_fee(*, policy: LateFeePolicy, outstanding: Decimal) -> Decimal:
    kind = policy.kind
    if kind == LateFeeKind.FLAT:
        return _q(policy.amount)
    # percent_of_outstanding / compound_percent both apply ``amount`` as a
    # fraction of the current outstanding balance.
    return _q(outstanding * Decimal(policy.amount))


def _as_utc(dt: datetime) -> datetime:
    """SQLite drops tzinfo from ``DateTime(timezone=True)`` columns; coerce."""
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt


def _gate_passes(
    *,
    policy: LateFeePolicy,
    invoice: Invoice,
    now: datetime,
) -> bool:
    """Return True if it's time to apply a fee against ``invoice``."""
    if invoice.due_at is None:
        return False
    if invoice.amount_outstanding <= _ZERO:
        return False
    due_at = _as_utc(invoice.due_at)
    # apply_after_days: wait this many days past due before first application.
    threshold = due_at + timedelta(days=int(policy.apply_after_days))
    if now < threshold:
        return False
    if invoice.last_late_fee_applied_at is None:
        return True
    # Already applied at least once. Only compound_percent re-applies.
    if policy.kind != LateFeeKind.COMPOUND_PERCENT:
        return False
    next_at = _as_utc(invoice.last_late_fee_applied_at) + timedelta(
        days=int(policy.compound_interval_days)
    )
    return now >= next_at


async def _resolve_late_fee_income_account(session: AsyncSession) -> uuid.UUID | None:
    raw = await SettingsService.get(
        "ar.default_late_fee_income_account_id", session=session
    )
    if raw is None:
        return None
    if isinstance(raw, uuid.UUID):
        return raw
    return uuid.UUID(str(raw))


async def apply_late_fees(
    session: AsyncSession,
    *,
    now: datetime | None = None,
    actor_user_id: uuid.UUID | None = None,
) -> list[LateFeeApplicationResult]:
    """Sweep overdue invoices and emit late-fee debit notes per policy."""
    now = now or datetime.now(UTC)
    income_account_override = await _resolve_late_fee_income_account(session)

    overdue_stmt = (
        select(Invoice)
        .where(Invoice.state == InvoiceState.OVERDUE)
        .where(Invoice.due_at.is_not(None))
        .where(Invoice.amount_outstanding > _ZERO)
    )
    invoices = list((await session.execute(overdue_stmt)).scalars().all())

    results: list[LateFeeApplicationResult] = []
    for invoice in invoices:
        policy = await _resolve_policy_for_customer(
            session, customer_id=invoice.customer_id
        )
        if policy is None:
            continue
        # Grace period: a "warning" window after due_at where we never fee.
        due_at = _as_utc(invoice.due_at) if invoice.due_at is not None else now
        grace_end = due_at + timedelta(days=int(policy.grace_period_days))
        if now < grace_end:
            continue
        if not _gate_passes(policy=policy, invoice=invoice, now=now):
            continue

        outstanding = Decimal(invoice.amount_outstanding)
        fee = _compute_fee(policy=policy, outstanding=outstanding)
        if fee <= _ZERO:
            continue

        effective_actor = actor_user_id or policy.created_by_user_id
        if effective_actor is None:
            log.warning(
                "late_fees.apply.skipped_no_actor",
                extra={"invoice_id": str(invoice.id), "policy_id": str(policy.id)},
            )
            continue

        # Build debit note → issue (with credit-side override) → apply.
        try:
            note = await debit_notes_service.create_draft(
                session,
                invoice_id=invoice.id,
                total_amount=fee,
                reason="late_fee",
                notes=None,
                actor_user_id=effective_actor,
            )
            await debit_notes_service.issue(
                session,
                debit_note_id=note.id,
                actor_user_id=effective_actor,
                revenue_account_id_override=income_account_override,
            )
            await debit_notes_service.apply(
                session,
                debit_note_id=note.id,
                actor_user_id=effective_actor,
            )
        except Exception:
            log.exception(
                "late_fees.apply.failed",
                extra={"invoice_id": str(invoice.id), "policy_id": str(policy.id)},
            )
            continue

        invoice.last_late_fee_applied_at = now
        days_overdue = (
            max((now - _as_utc(invoice.due_at)).days, 0) if invoice.due_at else 0
        )
        await session.flush()
        await _emit(
            session,
            event_type=ar_events.TYPE_LATE_FEE_APPLIED,
            aggregate_type=ar_events.AGGREGATE_TYPE_INVOICE,
            aggregate_id=invoice.id,
            payload={
                "invoice_id": str(invoice.id),
                "invoice_number": invoice.invoice_number,
                "customer_id": str(invoice.customer_id),
                "policy_id": str(policy.id),
                "debit_note_id": str(note.id),
                "amount": str(fee),
                "days_overdue": days_overdue,
            },
            actor_user_id=actor_user_id,
        )
        results.append(
            LateFeeApplicationResult(
                invoice_id=invoice.id,
                policy_id=policy.id,
                debit_note_id=note.id,
                amount=fee,
            )
        )
    return results


__all__ = [
    "InvalidLateFeePolicyError",
    "LateFeeApplicationResult",
    "LateFeePolicyNotFoundError",
    "LateFeesServiceError",
    "OverdueMarkResult",
    "apply_late_fees",
    "create_policy",
    "deactivate_policy",
    "get_policy",
    "list_policies",
    "mark_overdue",
    "update_policy",
]
