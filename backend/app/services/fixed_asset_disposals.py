"""Fixed-asset disposal service (Phase 9.4, #156).

Operator sells / scraps / writes off / donates a fixed asset. The
disposal flow is same-TX:

1. Validate the asset is ``active``.
2. Snapshot accumulated depreciation from the schedule (Σ of ``posted``
   entries with ``period_end <= disposed_on``).
3. Compute ``book_value = acquisition_cost - accumulated_depreciation``
   and ``gain_loss = proceeds_amount - book_value``.
4. Flip any ``planned`` schedule entries with ``period_end > disposed_on``
   to ``adjusted`` (cancel future depreciation).
5. Post a balanced JE:
     Dr Accumulated Depreciation (snapshot)
     Dr Proceeds account (if proceeds > 0)
     Cr Asset (acquisition_cost)
     Dr or Cr Gain/Loss (balancing — Cr for gain, Dr for loss)
6. Insert the ``fixed_asset_disposal`` row stamped with the JE id.
7. Flip ``asset.state`` to ``disposed`` (kind=sale or donation) or
   ``written_off`` (kind=scrap or writeoff).
8. Emit ``acc.AssetDisposed`` with the full disposal payload.

The router commits. Any raise rolls back row + JE + schedule mutations.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.events.types import accounting_assets as asset_events
from app.models.account import Account, AccountType
from app.models.depreciation_schedule import (
    DepreciationEntryState,
    DepreciationScheduleEntry,
)
from app.models.fixed_asset import FixedAsset, FixedAssetState
from app.models.fixed_asset_disposal import AssetDisposalKind, FixedAssetDisposal
from app.models.journal_entry import JournalEntry
from app.schemas.events import EventCreate
from app.services import event_store
from app.services import journal_entries as journal_service

# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class FixedAssetDisposalError(Exception):
    """Base. Routers default to 400."""


class AssetNotFoundError(FixedAssetDisposalError):
    """Mapped to 404."""


class AssetAlreadyDisposedError(FixedAssetDisposalError):
    """Asset state is already terminal."""


class InvalidDisposalInputError(FixedAssetDisposalError):
    """Bad inputs (amount, accounts, dates)."""


class InvalidAccountTypeError(FixedAssetDisposalError):
    """One of the supplied account_ids is the wrong COA type."""


# ---------------------------------------------------------------------------
# Decimal helpers
# ---------------------------------------------------------------------------

_QUANTUM = Decimal("0.000001")
_ZERO = Decimal("0")


def _q(value: Decimal | str | int | float) -> Decimal:
    if not isinstance(value, Decimal):
        value = Decimal(str(value))
    return value.quantize(_QUANTUM, rounding=ROUND_HALF_UP)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _load_account(session: AsyncSession, account_id: uuid.UUID) -> Account:
    acct = (
        await session.execute(select(Account).where(Account.id == account_id))
    ).scalar_one_or_none()
    if acct is None:
        raise InvalidDisposalInputError(f"account not found: {account_id}")
    if acct.is_archived:
        raise InvalidDisposalInputError(f"account {acct.code!r} is archived")
    return acct


def _ensure_account_type(account: Account, *, allowed: tuple[str, ...], role: str) -> None:
    actual = account.type.value if hasattr(account.type, "value") else account.type
    if actual not in allowed:
        raise InvalidAccountTypeError(
            f"account {account.code!r} has type {actual!r}; expected one of {allowed} for {role}"
        )


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
            aggregate_type=asset_events.AGGREGATE_TYPE_FIXED_ASSET,
            aggregate_id=aggregate_id,
            payload=payload,
            occurred_at=datetime.now(UTC),
            correlation_id=uuid.uuid4(),
            actor_user_id=actor_user_id,
        ),
        session=session,
    )


async def _snapshot_accumulated(
    session: AsyncSession, *, asset_id: uuid.UUID, disposed_on: date
) -> Decimal:
    rows = (
        (
            await session.execute(
                select(DepreciationScheduleEntry).where(
                    DepreciationScheduleEntry.asset_id == asset_id,
                    DepreciationScheduleEntry.state == DepreciationEntryState.POSTED,
                    DepreciationScheduleEntry.period_end <= disposed_on,
                )
            )
        )
        .scalars()
        .all()
    )
    return _q(sum((Decimal(r.depreciation_amount) for r in rows), _ZERO))


async def _cancel_future_planned(
    session: AsyncSession, *, asset_id: uuid.UUID, disposed_on: date
) -> int:
    rows = list(
        (
            await session.execute(
                select(DepreciationScheduleEntry).where(
                    DepreciationScheduleEntry.asset_id == asset_id,
                    DepreciationScheduleEntry.state == DepreciationEntryState.PLANNED,
                    DepreciationScheduleEntry.period_end > disposed_on,
                )
            )
        )
        .scalars()
        .all()
    )
    for entry in rows:
        entry.state = DepreciationEntryState.ADJUSTED
    if rows:
        await session.flush()
    return len(rows)


# ---------------------------------------------------------------------------
# dispose
# ---------------------------------------------------------------------------


_WRITTEN_OFF_KINDS = {AssetDisposalKind.SCRAP, AssetDisposalKind.WRITEOFF}


async def dispose(
    *,
    session: AsyncSession,
    asset_id: uuid.UUID,
    disposed_on: date,
    kind: str | AssetDisposalKind,
    proceeds_amount: Decimal | str | int | float = _ZERO,
    proceeds_account_id: uuid.UUID | None = None,
    gain_loss_account_id: uuid.UUID,
    notes: str | None = None,
    actor_user_id: uuid.UUID,
) -> FixedAssetDisposal:
    """Atomically dispose of a fixed asset.

    All work happens inside the caller's transaction; the router commits.
    Any raise rolls back the asset state flip, the schedule mutations,
    the JE, and the disposal row together.
    """
    # --- Normalize + validate scalars ---
    try:
        kind_e = AssetDisposalKind(kind) if not isinstance(kind, AssetDisposalKind) else kind
    except ValueError as exc:
        raise InvalidDisposalInputError(f"invalid kind: {kind!r}") from exc

    proceeds = _q(proceeds_amount)
    if proceeds < _ZERO:
        raise InvalidDisposalInputError("proceeds_amount must be >= 0")
    if proceeds > _ZERO and proceeds_account_id is None:
        raise InvalidDisposalInputError("proceeds_account_id is required when proceeds_amount > 0")
    if proceeds == _ZERO and proceeds_account_id is not None:
        raise InvalidDisposalInputError(
            "proceeds_account_id must be null when proceeds_amount is 0"
        )

    # --- Load + state-gate asset ---
    asset = (
        await session.execute(select(FixedAsset).where(FixedAsset.id == asset_id))
    ).scalar_one_or_none()
    if asset is None:
        raise AssetNotFoundError(str(asset_id))
    if asset.state != FixedAssetState.ACTIVE:
        raise AssetAlreadyDisposedError(
            f"asset {asset.asset_number} is in state {asset.state.value!r}; "
            "only active assets can be disposed"
        )
    if disposed_on < asset.acquired_on:
        raise InvalidDisposalInputError(
            f"disposed_on {disposed_on.isoformat()} is before "
            f"acquired_on {asset.acquired_on.isoformat()}"
        )

    # --- Account validation ---
    gain_loss_acct = await _load_account(session, gain_loss_account_id)
    _ensure_account_type(
        gain_loss_acct,
        allowed=(AccountType.REVENUE.value, AccountType.EXPENSE.value),
        role="gain_loss_account_id (P&L)",
    )

    proceeds_acct: Account | None = None
    if proceeds_account_id is not None:
        proceeds_acct = await _load_account(session, proceeds_account_id)
        _ensure_account_type(
            proceeds_acct,
            allowed=(AccountType.ASSET.value,),
            role="proceeds_account_id (Bank or AR)",
        )

    # --- Snapshot accumulated depreciation + book value ---
    accumulated = await _snapshot_accumulated(session, asset_id=asset.id, disposed_on=disposed_on)
    cost = _q(asset.acquisition_cost)
    book_value = _q(cost - accumulated)
    gain_loss = _q(proceeds - book_value)

    # --- Cancel any future planned entries ---
    cancelled_count = await _cancel_future_planned(
        session, asset_id=asset.id, disposed_on=disposed_on
    )

    # --- Build + post the JE ---
    posted_at = datetime.combine(disposed_on, datetime.min.time(), tzinfo=UTC)
    lines: list[journal_service.JournalLineInput] = []
    line_no = 1
    if accumulated > _ZERO:
        lines.append(
            journal_service.JournalLineInput(
                account_id=asset.accumulated_depreciation_account_id,
                debit=accumulated,
                credit=_ZERO,
                line_number=line_no,
                memo=f"Dr accumulated depreciation for {asset.asset_number}",
            )
        )
        line_no += 1
    if proceeds > _ZERO and proceeds_acct is not None:
        lines.append(
            journal_service.JournalLineInput(
                account_id=proceeds_acct.id,
                debit=proceeds,
                credit=_ZERO,
                line_number=line_no,
                memo=f"Dr proceeds for {asset.asset_number}",
            )
        )
        line_no += 1
    # Cr asset for full cost.
    lines.append(
        journal_service.JournalLineInput(
            account_id=asset.asset_account_id,
            debit=_ZERO,
            credit=cost,
            line_number=line_no,
            memo=f"Cr asset {asset.asset_number}",
        )
    )
    line_no += 1
    # Balancing gain/loss line. Gain = Cr; Loss = Dr.
    if gain_loss > _ZERO:
        lines.append(
            journal_service.JournalLineInput(
                account_id=gain_loss_acct.id,
                debit=_ZERO,
                credit=gain_loss,
                line_number=line_no,
                memo=f"Cr gain on disposal of {asset.asset_number}",
            )
        )
    elif gain_loss < _ZERO:
        lines.append(
            journal_service.JournalLineInput(
                account_id=gain_loss_acct.id,
                debit=-gain_loss,
                credit=_ZERO,
                line_number=line_no,
                memo=f"Dr loss on disposal of {asset.asset_number}",
            )
        )
    # gain_loss == 0 → no balancing line needed; the JE is already balanced.

    if len(lines) < 2:
        # Degenerate case (zero cost, zero accumulated, zero proceeds).
        raise InvalidDisposalInputError(
            "disposal has no economic effect (cost, accumulated depreciation, "
            "and proceeds are all zero)"
        )

    entry = await journal_service.post(
        journal_service.JournalEntryInput(
            description=f"Disposal of asset {asset.asset_number} ({kind_e.value})",
            posted_at=posted_at,
            lines=lines,
        ),
        session=session,
        actor_user_id=actor_user_id,
        _internal_skip_approval_check=True,
    )
    assert isinstance(entry, JournalEntry)

    # --- Insert disposal row + flip asset state ---
    disposal_id = uuid.uuid4()
    disposal = FixedAssetDisposal(
        id=disposal_id,
        asset_id=asset.id,
        disposed_on=disposed_on,
        disposal_kind=kind_e,
        proceeds_amount=proceeds,
        proceeds_account_id=proceeds_acct.id if proceeds_acct is not None else None,
        gain_loss_account_id=gain_loss_acct.id,
        book_value_at_disposal=book_value,
        accumulated_depreciation_at_disposal=accumulated,
        gain_loss_amount=gain_loss,
        notes=notes,
        posting_journal_entry_id=entry.id,
        created_by_user_id=actor_user_id,
    )
    session.add(disposal)

    if kind_e in _WRITTEN_OFF_KINDS:
        asset.state = FixedAssetState.WRITTEN_OFF
    else:
        asset.state = FixedAssetState.DISPOSED
    await session.flush()

    await _emit(
        session,
        event_type=asset_events.TYPE_ASSET_DISPOSED,
        aggregate_id=asset.id,
        payload={
            "asset_id": str(asset.id),
            "disposal_id": str(disposal.id),
            "disposed_on": disposed_on.isoformat(),
            # ``kind`` is the legacy field name from the reserved payload;
            # mirror ``disposal_kind`` for callers that want the explicit
            # name. Both are denormalized into the audit excerpt.
            "kind": kind_e.value,
            "disposal_kind": kind_e.value,
            "proceeds_amount": str(proceeds),
            "accumulated_depreciation": str(accumulated),
            "book_value": str(book_value),
            "gain_loss_amount": str(gain_loss),
            "journal_entry_id": str(entry.id),
            "cancelled_schedule_entries": cancelled_count,
        },
        actor_user_id=actor_user_id,
    )

    return disposal


async def get(session: AsyncSession, disposal_id: uuid.UUID) -> FixedAssetDisposal:
    row = (
        await session.execute(
            select(FixedAssetDisposal).where(FixedAssetDisposal.id == disposal_id)
        )
    ).scalar_one_or_none()
    if row is None:
        raise FixedAssetDisposalError(f"disposal not found: {disposal_id}")
    return row


__all__ = [
    "AssetAlreadyDisposedError",
    "AssetNotFoundError",
    "FixedAssetDisposalError",
    "InvalidAccountTypeError",
    "InvalidDisposalInputError",
    "dispose",
    "get",
]
