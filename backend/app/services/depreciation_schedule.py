"""Depreciation schedule generator (Phase 9.2, #154).

Generates the full month-by-month depreciation schedule for a fixed
asset at acquisition time. Stored as ``depreciation_schedule_entry``
rows in state ``planned``; Phase 9.3's worker walks the planned rows
and posts JEs, flipping the state to ``posted``.

Math
----
All math uses :class:`Decimal` with :data:`ROUND_HALF_UP` and the
``"0.01"`` quantum so amounts line up with the rest of the AR/AP stack.

* ``straight_line``: equal monthly amount = (cost - salvage) /
  useful_life_months, with the LAST month picking up the rounding
  remainder so ``sum(monthly entries) == depreciable_basis`` exactly.
  Final ``closing_book_value`` is ``salvage_value``.

* ``declining_balance_200`` / ``_150``: rate = K/N where K is 2 (200%)
  or 1.5 (150%) and N is useful_life_months. Each month's depreciation
  is the rounded ``book_value * rate``. When the next month would push
  the book value below ``salvage_value`` we CLAMP the month's
  depreciation to ``book_value - salvage_value`` so the closing book
  value lands exactly on salvage. Subsequent months emit
  zero-depreciation ``planned`` entries until ``useful_life_months`` is
  reached (this keeps every schedule the same length as the asset's
  useful life so Phase 9.3 / 9.4 can index by ``period_index`` without
  special cases).

* ``none``: returns ``[]``.

Idempotency
-----------
:func:`generate` is single-shot: if any entries already exist for the
asset it raises :class:`InvalidScheduleError`. :func:`recompute` (used
by 9.4 disposal flow once a partial recompute is needed) blocks if ANY
entry is already ``posted`` — for Phase 9.2 we do not support partial
recomputes.
"""

from __future__ import annotations

import calendar
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.events.types import accounting_assets as asset_events
from app.models.depreciation_schedule import (
    DepreciationEntryState,
    DepreciationScheduleEntry,
)
from app.models.fixed_asset import DepreciationMethod, FixedAsset
from app.schemas.events import EventCreate
from app.services import event_store

# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class DepreciationScheduleError(Exception):
    """Base error class."""


class InvalidScheduleError(DepreciationScheduleError):
    """Schedule already exists, or recompute attempted with posted rows."""


class AssetNotFoundError(DepreciationScheduleError):
    """No fixed_asset row for the given id."""


# ---------------------------------------------------------------------------
# Decimal helpers — match the AR/AP pattern (services/late_fees.py)
# ---------------------------------------------------------------------------

_QUANTUM = Decimal("0.01")
_ZERO = Decimal("0")


def _q(value: Decimal | str | int | float) -> Decimal:
    if not isinstance(value, Decimal):
        value = Decimal(str(value))
    return value.quantize(_QUANTUM, rounding=ROUND_HALF_UP)


# ---------------------------------------------------------------------------
# Pure computation
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ScheduleEntryRow:
    """A computed (pre-DB) schedule row.

    The DB ``DepreciationScheduleEntry`` mirrors these fields plus
    ``id``, ``state=planned``, ``journal_entry_id=None`` and timestamps.
    """

    period_index: int
    period_end: date
    opening_book_value: Decimal
    depreciation_amount: Decimal
    closing_book_value: Decimal


def _add_months(d: date, months: int) -> date:
    """Return ``d`` shifted forward by ``months`` months, clamped to the
    last day of the target month.

    Avoids the dateutil dependency for a small helper — the rest of the
    service only needs month-end shifts off ``acquired_on``.
    """
    if months < 0:
        raise ValueError("months must be >= 0")
    year = d.year + (d.month - 1 + months) // 12
    month = (d.month - 1 + months) % 12 + 1
    last_day = calendar.monthrange(year, month)[1]
    day = min(d.day, last_day)
    return date(year, month, day)


def _period_end_for(acquired_on: date, period_index: int) -> date:
    """End-of-period date for ``period_index`` (0-based month index)."""
    target = _add_months(acquired_on, period_index)
    last_day = calendar.monthrange(target.year, target.month)[1]
    return date(target.year, target.month, last_day)


def compute_entries(*, asset: FixedAsset) -> list[ScheduleEntryRow]:
    """Pure: returns the schedule rows. No DB."""
    method = (
        asset.depreciation_method.value
        if hasattr(asset.depreciation_method, "value")
        else str(asset.depreciation_method)
    )
    if method == DepreciationMethod.NONE.value:
        return []

    cost = _q(asset.acquisition_cost)
    salvage = _q(asset.salvage_value)
    n = int(asset.useful_life_months)
    basis = cost - salvage
    if basis <= _ZERO or n <= 0:
        return []

    if method == DepreciationMethod.STRAIGHT_LINE.value:
        return _compute_straight_line(asset.acquired_on, cost, salvage, n)
    if method == DepreciationMethod.DECLINING_BALANCE_200.value:
        return _compute_declining(asset.acquired_on, cost, salvage, n, rate_numerator=Decimal("2"))
    if method == DepreciationMethod.DECLINING_BALANCE_150.value:
        return _compute_declining(
            asset.acquired_on, cost, salvage, n, rate_numerator=Decimal("1.5")
        )
    raise InvalidScheduleError(f"unsupported depreciation_method: {method!r}")


def _compute_straight_line(
    acquired_on: date, cost: Decimal, salvage: Decimal, n: int
) -> list[ScheduleEntryRow]:
    basis = cost - salvage
    per_month = _q(basis / Decimal(n))
    rows: list[ScheduleEntryRow] = []
    book = cost
    running = _ZERO
    for i in range(n):
        # Last month picks up the rounding remainder so the sum
        # equals ``basis`` exactly.
        dep = per_month if i < n - 1 else basis - running
        opening = book
        closing = _q(opening - dep)
        rows.append(
            ScheduleEntryRow(
                period_index=i,
                period_end=_period_end_for(acquired_on, i),
                opening_book_value=opening,
                depreciation_amount=dep,
                closing_book_value=closing,
            )
        )
        running += dep
        book = closing
    return rows


def _compute_declining(
    acquired_on: date,
    cost: Decimal,
    salvage: Decimal,
    n: int,
    *,
    rate_numerator: Decimal,
) -> list[ScheduleEntryRow]:
    rate = rate_numerator / Decimal(n)
    rows: list[ScheduleEntryRow] = []
    book = cost
    salvage_reached = False
    for i in range(n):
        opening = book
        if salvage_reached:
            dep = _ZERO
        else:
            raw = opening * rate
            dep = _q(raw)
            # Clamp: never let book drop below salvage, and force the
            # last month to settle on salvage exactly.
            if opening - dep < salvage or i == n - 1:
                dep = _q(opening - salvage)
                salvage_reached = True
        closing = _q(opening - dep)
        rows.append(
            ScheduleEntryRow(
                period_index=i,
                period_end=_period_end_for(acquired_on, i),
                opening_book_value=opening,
                depreciation_amount=dep,
                closing_book_value=closing,
            )
        )
        book = closing
    return rows


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------


async def _load_asset(session: AsyncSession, asset_id: uuid.UUID) -> FixedAsset:
    row = (
        await session.execute(select(FixedAsset).where(FixedAsset.id == asset_id))
    ).scalar_one_or_none()
    if row is None:
        raise AssetNotFoundError(str(asset_id))
    return row


async def _load_entries(
    session: AsyncSession, asset_id: uuid.UUID
) -> list[DepreciationScheduleEntry]:
    stmt = (
        select(DepreciationScheduleEntry)
        .where(DepreciationScheduleEntry.asset_id == asset_id)
        .order_by(DepreciationScheduleEntry.period_index)
    )
    return list((await session.execute(stmt)).scalars().all())


async def _emit(
    session: AsyncSession,
    *,
    event_type: str,
    aggregate_id: uuid.UUID,
    payload: dict[str, Any],
    actor_user_id: uuid.UUID | None = None,
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


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def generate(
    *,
    session: AsyncSession,
    asset_id: uuid.UUID,
    actor_user_id: uuid.UUID | None = None,
) -> list[DepreciationScheduleEntry]:
    """Compute + INSERT the full schedule for ``asset_id``.

    Called inside ``fixed_assets.acquire`` in the SAME DB transaction;
    any raise rolls back the asset row too. Idempotent only in the sense
    that re-calling raises :class:`InvalidScheduleError`.
    """
    asset = await _load_asset(session, asset_id)

    existing = await _load_entries(session, asset_id)
    if existing:
        raise InvalidScheduleError(
            f"asset {asset_id} already has {len(existing)} schedule entries; "
            "use recompute() to rebuild"
        )

    rows = compute_entries(asset=asset)
    inserted: list[DepreciationScheduleEntry] = []
    for r in rows:
        entry = DepreciationScheduleEntry(
            asset_id=asset_id,
            period_index=r.period_index,
            period_end=r.period_end,
            opening_book_value=r.opening_book_value,
            depreciation_amount=r.depreciation_amount,
            closing_book_value=r.closing_book_value,
            state=DepreciationEntryState.PLANNED,
        )
        session.add(entry)
        inserted.append(entry)
    if inserted:
        await session.flush()

    method = (
        asset.depreciation_method.value
        if hasattr(asset.depreciation_method, "value")
        else str(asset.depreciation_method)
    )
    total = sum((r.depreciation_amount for r in rows), _ZERO)
    await _emit(
        session,
        event_type=asset_events.TYPE_DEPRECIATION_SCHEDULE_GENERATED,
        aggregate_id=asset_id,
        payload={
            "asset_id": str(asset_id),
            "total_entries": len(inserted),
            "total_depreciation": str(_q(total)) if total != _ZERO else "0.00",
            "method": method,
        },
        actor_user_id=actor_user_id,
    )
    return inserted


async def recompute(
    *,
    session: AsyncSession,
    asset_id: uuid.UUID,
    from_period_index: int = 0,
    actor_user_id: uuid.UUID | None = None,
) -> list[DepreciationScheduleEntry]:
    """Rebuild the schedule from scratch.

    Phase 9.2 does NOT support partial recomputes — if ANY entry is
    already ``posted`` this raises :class:`InvalidScheduleError`.
    Phase 9.4 (disposal) handles in-flight cancellation.
    """
    asset = await _load_asset(session, asset_id)
    existing = await _load_entries(session, asset_id)

    posted = [e for e in existing if e.state == DepreciationEntryState.POSTED]
    if posted:
        raise InvalidScheduleError(
            f"asset {asset_id} has {len(posted)} posted schedule entries; "
            "no partial recompute in Phase 9.2 (Phase 9.4 disposal handles "
            "in-flight cancellation)"
        )
    if from_period_index < 0:
        raise InvalidScheduleError("from_period_index must be >= 0")

    # Delete every existing entry (all are planned/adjusted) and rebuild.
    for e in existing:
        await session.delete(e)
    await session.flush()

    rows = compute_entries(asset=asset)
    inserted: list[DepreciationScheduleEntry] = []
    for r in rows:
        entry = DepreciationScheduleEntry(
            asset_id=asset_id,
            period_index=r.period_index,
            period_end=r.period_end,
            opening_book_value=r.opening_book_value,
            depreciation_amount=r.depreciation_amount,
            closing_book_value=r.closing_book_value,
            state=DepreciationEntryState.PLANNED,
        )
        session.add(entry)
        inserted.append(entry)
    if inserted:
        await session.flush()

    await _emit(
        session,
        event_type=asset_events.TYPE_DEPRECIATION_SCHEDULE_RECOMPUTED,
        aggregate_id=asset_id,
        payload={
            "asset_id": str(asset_id),
            "from_period_index": from_period_index,
            "total_recomputed": len(inserted),
        },
        actor_user_id=actor_user_id,
    )
    return inserted


async def get_schedule(
    *, session: AsyncSession, asset_id: uuid.UUID
) -> list[DepreciationScheduleEntry]:
    """Return all entries for an asset, ordered by ``period_index``."""
    # Ensure asset exists so the caller can map to a 404.
    await _load_asset(session, asset_id)
    return await _load_entries(session, asset_id)


__all__ = [
    "AssetNotFoundError",
    "DepreciationScheduleError",
    "InvalidScheduleError",
    "ScheduleEntryRow",
    "compute_entries",
    "generate",
    "get_schedule",
    "recompute",
]
