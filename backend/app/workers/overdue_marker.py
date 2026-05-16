"""Overdue invoice marker worker (Phase 7.6, #114).

Runs every 6 hours (``cron('0 */6 * * *')``). Calls
:func:`app.services.late_fees.mark_overdue` to scan invoices where
``due_at < now()`` and ``state IN (issued, partially_paid)`` and flip
them to ``overdue`` while emitting ``ar.InvoiceOverdue``. Idempotent —
re-running on the same day is a no-op because already-overdue invoices
fall out of the filter.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.services import late_fees as service
from app.workers.registry import register_job

log = logging.getLogger(__name__)

JOB_NAME = "overdue_marker"
CRON = "0 */6 * * *"


async def run(session: AsyncSession) -> None:
    now = datetime.now(UTC)
    result = await service.mark_overdue(session=session, now=now)
    await session.commit()
    log.info(
        "overdue_marker.marked",
        extra={"count": len(result.invoice_ids), "now": now.isoformat()},
    )


register_job(
    JOB_NAME,
    cron=CRON,
    fn=run,
    description="Flip past-due invoices to OVERDUE state (every 6 hours).",
)
