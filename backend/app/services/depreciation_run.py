"""Depreciation run service (Phase 9.3, #155).

Walks ``depreciation_schedule_entry`` rows whose ``state='planned'`` and
``period_end <= run_period_end`` and, for each, posts a balanced JE
(Dr Depreciation Expense / Cr Accumulated Depreciation), stamps the
entry's ``journal_entry_id``, flips its state to ``posted``, and updates
the asset's ``last_depreciated_on``.

Idempotency
-----------
The selector filters on ``state='planned'`` so a re-run for the same
period is a no-op against entries already flipped to ``posted``.

Per-asset exception handling
----------------------------
Each entry is posted in its own logical sub-transaction. If posting one
entry raises (e.g. mis-configured account, period closed, JE
unbalanced), we ``session.rollback()`` and continue with the next entry.
Successful entries are committed immediately so a mid-run crash does
not lose progress.

A trailing ``acc.DepreciationRunCompleted`` event captures the totals
for the audit log.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.events.types import accounting_assets as asset_events
from app.models.depreciation_schedule import (
    DepreciationEntryState,
    DepreciationScheduleEntry,
)
from app.models.fixed_asset import FixedAsset
from app.models.journal_entry import JournalEntry
from app.schemas.events import EventCreate
from app.services import event_store
from app.services import journal_entries as journal_service

log = logging.getLogger(__name__)


_ZERO = Decimal("0")


@dataclass(frozen=True)
class DepreciationRunResult:
    period_end: date
    posted_count: int
    failed_count: int
    posted_entry_ids: list[uuid.UUID]


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
            aggregate_type=asset_events.AGGREGATE_TYPE_DEPRECIATION_SCHEDULE,
            aggregate_id=aggregate_id,
            payload=payload,
            occurred_at=datetime.now(UTC),
            correlation_id=uuid.uuid4(),
            actor_user_id=actor_user_id,
        ),
        session=session,
    )


async def _post_one_entry(
    session: AsyncSession,
    *,
    asset: FixedAsset,
    entry: DepreciationScheduleEntry,
    actor_user_id: uuid.UUID,
) -> uuid.UUID:
    """Post a single depreciation entry's JE in the current TX.

    Caller is responsible for committing (success) or rolling back
    (exception).
    """
    posted_at = datetime.combine(entry.period_end, datetime.min.time(), tzinfo=UTC)
    je = await journal_service.post(
        journal_service.JournalEntryInput(
            description=(
                f"Depreciation of {asset.asset_number} period "
                f"{entry.period_end.isoformat()} (#{entry.period_index})"
            ),
            posted_at=posted_at,
            lines=[
                journal_service.JournalLineInput(
                    account_id=asset.depreciation_expense_account_id,
                    debit=entry.depreciation_amount,
                    credit=_ZERO,
                    line_number=1,
                    memo=f"Dr depreciation expense for {asset.asset_number}",
                ),
                journal_service.JournalLineInput(
                    account_id=asset.accumulated_depreciation_account_id,
                    debit=_ZERO,
                    credit=entry.depreciation_amount,
                    line_number=2,
                    memo=f"Cr accumulated depreciation for {asset.asset_number}",
                ),
            ],
        ),
        session=session,
        actor_user_id=actor_user_id,
        _internal_skip_approval_check=True,
    )
    assert isinstance(je, JournalEntry)

    entry.journal_entry_id = je.id
    entry.state = DepreciationEntryState.POSTED
    asset.last_depreciated_on = entry.period_end
    await session.flush()

    await _emit(
        session,
        event_type=asset_events.TYPE_DEPRECIATION_POSTED,
        aggregate_id=asset.id,
        payload={
            "asset_id": str(asset.id),
            "entry_id": str(entry.id),
            "journal_entry_id": str(je.id),
            "period_end": entry.period_end.isoformat(),
            "period_index": entry.period_index,
            "amount": str(entry.depreciation_amount),
        },
        actor_user_id=actor_user_id,
    )
    return je.id


async def run_for_period(
    *,
    session: AsyncSession,
    period_end: date,
    actor_user_id: uuid.UUID | None = None,
) -> DepreciationRunResult:
    """Post all ``planned`` entries whose ``period_end <= period_end``.

    Commits after every successful entry. On failure for one asset, the
    sub-TX is rolled back and the run continues. The trailing
    ``DepreciationRunCompleted`` event is committed at the end.
    """
    # Collect IDs up-front so a per-entry rollback (which expires all
    # in-session ORM objects) doesn't trip us up on the next iteration —
    # we reload by id per loop instead of holding stale ORM rows.
    id_stmt = (
        select(DepreciationScheduleEntry.id)
        .where(DepreciationScheduleEntry.state == DepreciationEntryState.PLANNED)
        .where(DepreciationScheduleEntry.period_end <= period_end)
        .order_by(
            DepreciationScheduleEntry.period_end,
            DepreciationScheduleEntry.asset_id,
            DepreciationScheduleEntry.period_index,
        )
    )
    entry_ids = list((await session.execute(id_stmt)).scalars().all())

    posted_entry_ids: list[uuid.UUID] = []
    failed = 0

    for entry_id in entry_ids:
        entry = (
            await session.execute(
                select(DepreciationScheduleEntry).where(DepreciationScheduleEntry.id == entry_id)
            )
        ).scalar_one_or_none()
        if entry is None or entry.state != DepreciationEntryState.PLANNED:
            continue
        asset = (
            await session.execute(select(FixedAsset).where(FixedAsset.id == entry.asset_id))
        ).scalar_one_or_none()
        if asset is None:
            log.error(
                "depreciation_run.asset_missing",
                extra={"entry_id": str(entry.id), "asset_id": str(entry.asset_id)},
            )
            failed += 1
            continue

        effective_actor = actor_user_id or asset.created_by_user_id
        try:
            await _post_one_entry(
                session,
                asset=asset,
                entry=entry,
                actor_user_id=effective_actor,
            )
            await session.commit()
            posted_entry_ids.append(entry.id)
        except Exception:
            await session.rollback()
            failed += 1
            log.exception(
                "depreciation_run.entry_failed",
                extra={"entry_id": str(entry_id)},
            )
            continue

    await _emit(
        session,
        event_type=asset_events.TYPE_DEPRECIATION_RUN_COMPLETED,
        aggregate_id=uuid.uuid4(),
        payload={
            "period_end": period_end.isoformat(),
            "posted_count": len(posted_entry_ids),
            "failed_count": failed,
        },
        actor_user_id=actor_user_id,
    )
    await session.commit()

    return DepreciationRunResult(
        period_end=period_end,
        posted_count=len(posted_entry_ids),
        failed_count=failed,
        posted_entry_ids=posted_entry_ids,
    )


def previous_month_end(now: datetime) -> date:
    """Return the last day of the calendar month preceding ``now``."""
    today = now.astimezone(UTC).date() if now.tzinfo is not None else now.date()
    first_of_current = date(today.year, today.month, 1)
    return date.fromordinal(first_of_current.toordinal() - 1)


__all__ = [
    "DepreciationRunResult",
    "previous_month_end",
    "run_for_period",
]
