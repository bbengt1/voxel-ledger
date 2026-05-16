"""Overdue bill marker worker (Phase 8.4, #131).

Runs every 6 hours (``cron('0 */6 * * *')``). Calls
:func:`app.services.bill_overdue.mark_overdue` to scan bills where
``due_at < now()`` and ``state IN (issued, partially_paid)`` and flip
them to ``overdue`` while emitting ``ap.BillOverdue``. Idempotent —
re-running on the same day is a no-op because already-overdue bills
fall out of the filter.

Mirror of :mod:`app.workers.overdue_marker` for the AP bounded context.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.services import bill_overdue as service
from app.workers.registry import register_job

log = logging.getLogger(__name__)

JOB_NAME = "overdue_bill_marker"
CRON = "0 */6 * * *"


async def run(session: AsyncSession) -> None:
    now = datetime.now(UTC)
    result = await service.mark_overdue(session=session, now=now)
    await session.commit()
    log.info(
        "overdue_bill_marker.marked",
        extra={"count": len(result.bill_ids), "now": now.isoformat()},
    )


register_job(
    JOB_NAME,
    cron=CRON,
    fn=run,
    description="Flip past-due bills to OVERDUE state (every 6 hours).",
)
