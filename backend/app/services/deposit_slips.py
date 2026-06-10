"""Deposit slips service (Parity #235).

Builds a single bank-deposit JE that moves N customer-payment
applications from the undeposited-funds clearing account to the
bank account. Matches how the bank statement reports it (one
consolidated deposit, not N separate credits).

Flow:

  1. Customer pays. The operator marks the payment with
     ``deposit_to_undeposited=True``. Apply-payment then debits the
     undeposited clearing account instead of the bank account.
  2. At the end of the day (or per-bank-trip) the operator selects
     N undeposited payments + a bank account + deposit date and
     calls ``build_slip``.
  3. ``build_slip`` posts one JE: DR the bank account for the
     consolidated total, CR the undeposited account by the same
     amount. State flips to ``deposited``.
  4. Bank reconciliation later matches the slip total against the
     real bank statement; the slip flips to ``reconciled``.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.events.types import ar as ar_events
from app.models.deposit_slip import DepositSlip, DepositSlipItem, DepositSlipState
from app.models.journal_entry import JournalEntry
from app.models.payment import Payment
from app.schemas.events import EventCreate
from app.services import event_store
from app.services import journal_entries as journal_service
from app.services.payments import _resolve_undeposited_account
from app.services.reference_number import ReferenceNumberService

_QUANTUM = Decimal("0.01")
_ZERO = Decimal("0")


def _q(value: Decimal) -> Decimal:
    return value.quantize(_QUANTUM, rounding=ROUND_HALF_UP)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class DepositSlipServiceError(Exception):
    """Base. Routers map to 400."""


class DepositSlipNotFoundError(DepositSlipServiceError):
    """Mapped to 404."""


class DepositSlipInvalidPaymentsError(DepositSlipServiceError):
    """One or more of the supplied payments isn't eligible."""


class DepositSlipBankAccountMissingError(DepositSlipServiceError):
    """The bank_account_id setting isn't configured."""


# ---------------------------------------------------------------------------
# Build slip
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BuildResult:
    slip_id: uuid.UUID
    slip_number: str
    # None in QBO replace-mode (epic #312): pushed async via the sync outbox.
    journal_entry_id: uuid.UUID | None
    total: Decimal


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
            aggregate_type=ar_events.AGGREGATE_TYPE_PAYMENT,
            aggregate_id=aggregate_id,
            payload=payload,
            occurred_at=datetime.now(UTC),
            correlation_id=uuid.uuid4(),
            actor_user_id=actor_user_id,
        ),
        session=session,
    )


async def build_slip(
    session: AsyncSession,
    *,
    payment_ids: list[uuid.UUID],
    bank_account_id: uuid.UUID,
    deposit_date: date,
    actor_user_id: uuid.UUID | None,
) -> BuildResult:
    """Consolidate N undeposited payments into a bank deposit JE.

    Pre-checks: every payment in ``payment_ids`` must exist, have
    ``deposit_to_undeposited=True``, not already be linked to a slip
    item, and have its application already posted (state ``applied``
    or later). The undeposited setting must resolve.
    """
    if not payment_ids:
        raise DepositSlipInvalidPaymentsError("payment_ids cannot be empty")

    # Single fetch + assert eligibility per payment.
    payments = (
        (await session.execute(select(Payment).where(Payment.id.in_(payment_ids)))).scalars().all()
    )
    found = {p.id: p for p in payments}
    missing = [pid for pid in payment_ids if pid not in found]
    if missing:
        raise DepositSlipInvalidPaymentsError(f"payments not found: {missing}")

    for p in found.values():
        if not bool(p.deposit_to_undeposited):
            raise DepositSlipInvalidPaymentsError(
                f"payment {p.payment_number} is not flagged " "deposit_to_undeposited"
            )

    # Already on another slip?
    already = (
        (
            await session.execute(
                select(DepositSlipItem.payment_id).where(
                    DepositSlipItem.payment_id.in_(payment_ids)
                )
            )
        )
        .scalars()
        .all()
    )
    if already:
        raise DepositSlipInvalidPaymentsError(
            f"payments already on a deposit slip: {list(already)}"
        )

    # QBO replace-mode (epic #312, Phase 3d-2): enqueue a role-tagged JournalEntry
    # (Dr bank, Cr undeposited_funds) instead of posting the local GL.
    from app.services.quickbooks import outbox as qbo_outbox

    qbo_enabled = await qbo_outbox.is_enabled(session)
    undeposited_account_id = None if qbo_enabled else await _resolve_undeposited_account(session)

    total = _q(sum((p.amount for p in found.values()), _ZERO))
    if total <= _ZERO:
        raise DepositSlipInvalidPaymentsError("slip total must be > 0")

    slip_number = await ReferenceNumberService.allocate("DS", session=session)
    slip_id = uuid.uuid4()

    # Post the consolidated transfer JE: DR bank for the total, CR
    # undeposited for the total. The customer-payment apply-payment
    # JEs already moved AR -> undeposited; this completes the chain
    # to AR -> bank.
    je_id: uuid.UUID | None = None
    if qbo_enabled:
        await qbo_outbox.enqueue(
            session,
            kind="deposit_slip",
            local_id=slip_id,
            payload={
                "lines": [
                    {"role": "bank", "posting": "debit", "amount": str(total)},
                    {"role": "undeposited_funds", "posting": "credit", "amount": str(total)},
                ],
                "private_note": f"Deposit slip {slip_number}",
            },
            op="post",
        )
    else:
        je = await journal_service.post(
            journal_service.JournalEntryInput(
                description=f"Deposit slip {slip_number}",
                posted_at=datetime.combine(deposit_date, datetime.min.time(), tzinfo=UTC),
                lines=[
                    journal_service.JournalLineInput(
                        account_id=bank_account_id,
                        debit=total,
                        credit=_ZERO,
                        line_number=1,
                        memo=f"Deposit {slip_number} (consolidated)",
                    ),
                    journal_service.JournalLineInput(
                        account_id=undeposited_account_id,
                        debit=_ZERO,
                        credit=total,
                        line_number=2,
                        memo=f"Clear undeposited for slip {slip_number}",
                    ),
                ],
            ),
            session=session,
            actor_user_id=actor_user_id,
            _internal_skip_approval_check=True,
        )
        if not isinstance(je, JournalEntry):
            raise DepositSlipServiceError(
                "deposit-slip JE generated an approval request unexpectedly"
            )
        je_id = je.id

    slip = DepositSlip(
        id=slip_id,
        slip_number=slip_number,
        bank_account_id=bank_account_id,
        deposit_date=deposit_date,
        total_amount=total,
        state=DepositSlipState.DEPOSITED,
        posting_journal_entry_id=je_id,
        created_by_user_id=actor_user_id,
    )
    session.add(slip)
    for p in found.values():
        session.add(
            DepositSlipItem(
                id=uuid.uuid4(),
                deposit_slip_id=slip_id,
                payment_id=p.id,
                amount=_q(p.amount),
            )
        )
    await session.flush()

    await _emit(
        session,
        event_type="ar.DepositSlipBuilt",
        aggregate_id=slip_id,
        payload={
            "slip_id": str(slip_id),
            "slip_number": slip_number,
            "bank_account_id": str(bank_account_id),
            "deposit_date": deposit_date.isoformat(),
            "total": str(total),
            "payment_ids": [str(pid) for pid in payment_ids],
            "journal_entry_id": str(je_id) if je_id else None,
        },
        actor_user_id=actor_user_id,
    )

    return BuildResult(
        slip_id=slip_id,
        slip_number=slip_number,
        journal_entry_id=je_id,
        total=total,
    )


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------


async def list_undeposited_payments(session: AsyncSession) -> list[Payment]:
    """Payments flagged for undeposited that aren't on any slip yet."""
    on_slip = select(DepositSlipItem.payment_id)
    stmt = (
        select(Payment)
        .where(Payment.deposit_to_undeposited.is_(True))
        .where(Payment.id.not_in(on_slip))
        .order_by(Payment.received_at.asc())
    )
    return list((await session.execute(stmt)).scalars().all())


async def get_slip(session: AsyncSession, slip_id: uuid.UUID) -> DepositSlip:
    row = (
        await session.execute(select(DepositSlip).where(DepositSlip.id == slip_id))
    ).scalar_one_or_none()
    if row is None:
        raise DepositSlipNotFoundError(str(slip_id))
    return row


async def list_slips(session: AsyncSession) -> list[DepositSlip]:
    return list(
        (await session.execute(select(DepositSlip).order_by(DepositSlip.deposit_date.desc())))
        .scalars()
        .all()
    )


__all__ = [
    "BuildResult",
    "DepositSlipBankAccountMissingError",
    "DepositSlipInvalidPaymentsError",
    "DepositSlipNotFoundError",
    "DepositSlipServiceError",
    "build_slip",
    "get_slip",
    "list_slips",
    "list_undeposited_payments",
]
