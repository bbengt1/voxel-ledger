"""Bank reconciliation service (Phase 8.11, #138).

The reconciliation workflow:

1. Operator opens a reconciliation with ``create()``, supplying the
   statement's ending balance + period. The service pre-populates items
   from every ``bank_transaction`` row in the period whose ``state``
   isn't ``ignored``. Items mirror the transaction state at open time
   (rows already ``matched`` / ``cleared`` arrive as ``is_cleared=True``;
   ``unmatched`` rows arrive ``False`` and the operator ticks them).

2. The operator flips ``is_cleared`` on individual items with
   :func:`toggle_cleared`. Each toggle re-runs the balance recompute so
   the difference stays accurate on screen. ``state`` flips to
   ``balanced`` when ``|difference| <= tolerance``.

3. :func:`finalize` is gated by the same tolerance check. On finalize
   the service stamps ``finalized_at`` / ``finalized_by_user_id``, flips
   ``state`` to ``finalized``, and flips each cleared item's underlying
   ``bank_transaction.state`` to ``cleared``.

Same-TX: NO ``await session.commit()`` inside this service. The router
owns the commit.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import asc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.events.types import banking as banking_events
from app.models.account import Account
from app.models.bank import BankTransaction, BankTransactionState
from app.models.bank_reconciliation import (
    BankReconciliation,
    BankReconciliationItem,
    BankReconciliationState,
)
from app.schemas.events import EventCreate
from app.services import event_store
from app.services.settings.service import SettingsService


class BankReconciliationServiceError(Exception):
    """Base. Routers map to 400 unless noted."""


class BankReconciliationNotFoundError(BankReconciliationServiceError):
    """Mapped to 404."""


class BankReconciliationItemNotFoundError(BankReconciliationServiceError):
    """Mapped to 404."""


class InvalidBankReconciliationError(BankReconciliationServiceError):
    """Validation failure."""


class BankReconciliationFinalizedError(BankReconciliationServiceError):
    """Attempted mutation against a finalized reconciliation."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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
            aggregate_type=banking_events.AGGREGATE_TYPE_BANK_RECONCILIATION,
            aggregate_id=aggregate_id,
            payload=payload,
            occurred_at=datetime.now(UTC),
            correlation_id=uuid.uuid4(),
            actor_user_id=actor_user_id,
        ),
        session=session,
    )


async def _load(session: AsyncSession, recon_id: uuid.UUID) -> BankReconciliation:
    row = (
        await session.execute(select(BankReconciliation).where(BankReconciliation.id == recon_id))
    ).scalar_one_or_none()
    if row is None:
        raise BankReconciliationNotFoundError(str(recon_id))
    return row


async def _load_item(session: AsyncSession, item_id: uuid.UUID) -> BankReconciliationItem:
    row = (
        await session.execute(
            select(BankReconciliationItem).where(BankReconciliationItem.id == item_id)
        )
    ).scalar_one_or_none()
    if row is None:
        raise BankReconciliationItemNotFoundError(str(item_id))
    return row


async def _load_items(session: AsyncSession, recon_id: uuid.UUID) -> list[BankReconciliationItem]:
    rows = (
        (
            await session.execute(
                select(BankReconciliationItem)
                .where(BankReconciliationItem.reconciliation_id == recon_id)
                .order_by(asc(BankReconciliationItem.id))
            )
        )
        .scalars()
        .all()
    )
    return list(rows)


async def _tolerance(session: AsyncSession) -> Decimal:
    raw = await SettingsService.get("banking.reconciliation_rounding_tolerance", session=session)
    if isinstance(raw, Decimal):
        return raw
    return Decimal(str(raw))


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


async def get(session: AsyncSession, recon_id: uuid.UUID) -> BankReconciliation:
    return await _load(session, recon_id)


async def list_items(session: AsyncSession, recon_id: uuid.UUID) -> list[BankReconciliationItem]:
    return await _load_items(session, recon_id)


async def create(
    *,
    session: AsyncSession,
    account_id: uuid.UUID,
    period_start: date,
    period_end: date,
    statement_ending_balance: Decimal,
    actor_user_id: uuid.UUID,
    notes: str | None = None,
) -> BankReconciliation:
    if period_end < period_start:
        raise InvalidBankReconciliationError("period_end must be >= period_start")

    acct = (
        await session.execute(select(Account).where(Account.id == account_id))
    ).scalar_one_or_none()
    if acct is None:
        raise InvalidBankReconciliationError(f"account {account_id} does not exist")

    if not isinstance(statement_ending_balance, Decimal):
        statement_ending_balance = Decimal(str(statement_ending_balance))

    recon = BankReconciliation(
        account_id=account_id,
        period_start=period_start,
        period_end=period_end,
        statement_ending_balance=statement_ending_balance,
        state=BankReconciliationState.IN_PROGRESS,
        notes=(notes.strip() if isinstance(notes, str) and notes.strip() else None),
        created_by_user_id=actor_user_id,
    )
    session.add(recon)
    await session.flush()

    # Pre-populate items from every non-ignored bank_transaction in the
    # period. Initial is_cleared mirrors the transaction state (matched
    # or cleared rows arrive ticked).
    tx_rows = (
        (
            await session.execute(
                select(BankTransaction)
                .where(
                    BankTransaction.account_id == account_id,
                    BankTransaction.occurred_on >= period_start,
                    BankTransaction.occurred_on <= period_end,
                    BankTransaction.state != BankTransactionState.IGNORED,
                )
                .order_by(asc(BankTransaction.occurred_on), asc(BankTransaction.id))
            )
        )
        .scalars()
        .all()
    )
    for tx in tx_rows:
        item = BankReconciliationItem(
            reconciliation_id=recon.id,
            bank_transaction_id=tx.id,
            is_cleared=tx.state in (BankTransactionState.CLEARED, BankTransactionState.MATCHED),
        )
        session.add(item)
    await session.flush()

    # Initial balance recompute (so book_ending_balance + difference are
    # set before the operator sees the screen).
    await _recompute_inplace(session, recon)

    await _emit(
        session,
        event_type=banking_events.TYPE_BANK_RECONCILIATION_OPENED,
        aggregate_id=recon.id,
        payload={
            "recon_id": str(recon.id),
            "account_id": str(recon.account_id),
            "period_start": recon.period_start.isoformat(),
            "period_end": recon.period_end.isoformat(),
            "statement_ending_balance": str(recon.statement_ending_balance),
        },
        actor_user_id=actor_user_id,
    )
    return recon


async def _recompute_inplace(
    session: AsyncSession, recon: BankReconciliation
) -> BankReconciliation:
    """Compute book_ending_balance + difference + state on the in-memory row.

    Sum the signed amounts of all cleared items' bank transactions. We
    join via a single query so this is cheap regardless of period size.
    """
    stmt = (
        select(BankTransaction.amount)
        .join(
            BankReconciliationItem,
            BankReconciliationItem.bank_transaction_id == BankTransaction.id,
        )
        .where(
            BankReconciliationItem.reconciliation_id == recon.id,
            BankReconciliationItem.is_cleared.is_(True),
        )
    )
    amounts = list((await session.execute(stmt)).scalars().all())
    book = sum(amounts, Decimal("0")) if amounts else Decimal("0")
    diff = recon.statement_ending_balance - book
    recon.book_ending_balance = book
    recon.difference = diff

    if recon.state != BankReconciliationState.FINALIZED:
        tolerance = await _tolerance(session)
        if abs(diff) <= tolerance:
            recon.state = BankReconciliationState.BALANCED
        else:
            recon.state = BankReconciliationState.IN_PROGRESS

    await session.flush()
    return recon


async def recompute_balance(
    *,
    session: AsyncSession,
    reconciliation_id: uuid.UUID,
) -> BankReconciliation:
    recon = await _load(session, reconciliation_id)
    if recon.state == BankReconciliationState.FINALIZED:
        # Finalized recons are frozen — recompute is a no-op.
        return recon
    return await _recompute_inplace(session, recon)


async def toggle_cleared(
    *,
    session: AsyncSession,
    item_id: uuid.UUID,
    is_cleared: bool,
    actor_user_id: uuid.UUID,
) -> BankReconciliationItem:
    item = await _load_item(session, item_id)
    recon = await _load(session, item.reconciliation_id)
    if recon.state == BankReconciliationState.FINALIZED:
        raise BankReconciliationFinalizedError("cannot modify items on a finalized reconciliation")
    if item.is_cleared == is_cleared:
        return item
    item.is_cleared = is_cleared
    await session.flush()

    await _recompute_inplace(session, recon)

    event_type = (
        banking_events.TYPE_BANK_RECONCILIATION_ITEM_CLEARED
        if is_cleared
        else banking_events.TYPE_BANK_RECONCILIATION_ITEM_UNCLEARED
    )
    await _emit(
        session,
        event_type=event_type,
        aggregate_id=recon.id,
        payload={
            "recon_id": str(recon.id),
            "item_id": str(item.id),
            "transaction_id": str(item.bank_transaction_id),
        },
        actor_user_id=actor_user_id,
    )
    return item


async def finalize(
    *,
    session: AsyncSession,
    reconciliation_id: uuid.UUID,
    actor_user_id: uuid.UUID,
) -> BankReconciliation:
    recon = await _load(session, reconciliation_id)
    if recon.state == BankReconciliationState.FINALIZED:
        raise BankReconciliationFinalizedError("reconciliation already finalized")

    # Always recompute before the tolerance check so we don't trust
    # stale on-row data.
    await _recompute_inplace(session, recon)
    tolerance = await _tolerance(session)
    diff = recon.difference if recon.difference is not None else Decimal("0")
    if abs(diff) > tolerance:
        raise InvalidBankReconciliationError(
            f"cannot finalize: difference {diff} exceeds tolerance {tolerance}"
        )

    # Flip underlying bank_transaction.state for each cleared item.
    items = await _load_items(session, recon.id)
    cleared_tx_ids = [i.bank_transaction_id for i in items if i.is_cleared]
    if cleared_tx_ids:
        tx_rows = (
            (
                await session.execute(
                    select(BankTransaction).where(BankTransaction.id.in_(cleared_tx_ids))
                )
            )
            .scalars()
            .all()
        )
        for tx in tx_rows:
            if tx.state != BankTransactionState.CLEARED:
                tx.state = BankTransactionState.CLEARED

    recon.state = BankReconciliationState.FINALIZED
    recon.finalized_at = datetime.now(UTC)
    recon.finalized_by_user_id = actor_user_id
    await session.flush()

    await _emit(
        session,
        event_type=banking_events.TYPE_BANK_RECONCILIATION_FINALIZED,
        aggregate_id=recon.id,
        payload={
            "recon_id": str(recon.id),
            "account_id": str(recon.account_id),
            "period_end": recon.period_end.isoformat(),
            "book_ending_balance": str(
                recon.book_ending_balance if recon.book_ending_balance is not None else Decimal("0")
            ),
            "statement_ending_balance": str(recon.statement_ending_balance),
            "difference": str(diff),
        },
        actor_user_id=actor_user_id,
    )
    return recon


async def list_reconciliations(
    *,
    session: AsyncSession,
    account_id: uuid.UUID | None = None,
    state: str | None = None,
    limit: int = 100,
) -> list[BankReconciliation]:
    stmt = select(BankReconciliation)
    if account_id is not None:
        stmt = stmt.where(BankReconciliation.account_id == account_id)
    if state is not None:
        # Accept either enum instance or string.
        try:
            state_enum = BankReconciliationState(state)
        except ValueError as exc:
            raise InvalidBankReconciliationError(f"invalid state {state!r}") from exc
        stmt = stmt.where(BankReconciliation.state == state_enum)
    stmt = stmt.order_by(
        BankReconciliation.period_end.desc(),
        asc(BankReconciliation.id),
    ).limit(limit)
    return list((await session.execute(stmt)).scalars().all())


__all__ = [
    "BankReconciliationFinalizedError",
    "BankReconciliationItemNotFoundError",
    "BankReconciliationNotFoundError",
    "BankReconciliationServiceError",
    "InvalidBankReconciliationError",
    "create",
    "finalize",
    "get",
    "list_items",
    "list_reconciliations",
    "recompute_balance",
    "toggle_cleared",
]
