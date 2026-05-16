"""Overdue-bill marker service (Phase 8.4, #131).

Mirror of the AR-side :func:`app.services.late_fees.mark_overdue` for the
AP bounded context: scans ``bill`` rows with ``due_at < now()`` and
``state IN (issued, partially_paid)`` and flips them to
:data:`BillState.OVERDUE` while emitting ``ap.BillOverdue``. The state
flip alone is idempotent — re-running on the same day is a no-op because
already-overdue bills fall out of the filter.

Phase 8 intentionally does NOT ship AP-side late-fee policies, so only the
overdue-marker piece of the AR pattern lands here.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.events.types import ap as ap_events
from app.models.bill import Bill, BillState
from app.schemas.events import EventCreate
from app.services import event_store


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


def _as_utc(dt: datetime) -> datetime:
    """SQLite drops tzinfo from ``DateTime(timezone=True)`` columns; coerce."""
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt


@dataclass(frozen=True)
class OverdueMarkResult:
    bill_ids: list[uuid.UUID]


async def mark_overdue(
    session: AsyncSession,
    *,
    now: datetime | None = None,
    actor_user_id: uuid.UUID | None = None,
) -> OverdueMarkResult:
    """Flip every newly-overdue bill and emit ``ap.BillOverdue``."""
    now = now or datetime.now(UTC)
    stmt = (
        select(Bill)
        .where(Bill.due_at.is_not(None))
        .where(Bill.due_at < now)
        .where(Bill.state.in_((BillState.ISSUED, BillState.PARTIALLY_PAID)))
    )
    rows = list((await session.execute(stmt)).scalars().all())
    marked: list[uuid.UUID] = []
    for bill in rows:
        days_overdue = max((now - _as_utc(bill.due_at)).days, 0) if bill.due_at else 0
        bill.state = BillState.OVERDUE
        await session.flush()
        await _emit(
            session,
            event_type=ap_events.TYPE_BILL_OVERDUE,
            aggregate_type=ap_events.AGGREGATE_TYPE_BILL,
            aggregate_id=bill.id,
            payload={
                "bill_id": str(bill.id),
                "bill_number": bill.bill_number,
                "vendor_id": str(bill.vendor_id),
                "due_at": bill.due_at.isoformat() if bill.due_at else "",
                "days_overdue": days_overdue,
                "amount_outstanding": str(bill.amount_outstanding),
            },
            actor_user_id=actor_user_id,
        )
        marked.append(bill.id)
    return OverdueMarkResult(bill_ids=marked)


__all__ = [
    "OverdueMarkResult",
    "mark_overdue",
]
