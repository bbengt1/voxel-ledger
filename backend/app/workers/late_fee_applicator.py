"""Late-fee applicator worker (Phase 7.6, #114).

Runs daily (``cron('0 1 * * *')``). Calls
:func:`app.services.late_fees.apply_late_fees` to sweep overdue invoices
and emit debit notes for each according to the resolved policy.
Idempotency is anchored on ``invoice.last_late_fee_applied_at`` so a
re-run within a policy's ``compound_interval_days`` is a no-op.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.services import late_fees as service
from app.workers.registry import register_job

log = logging.getLogger(__name__)

JOB_NAME = "late_fee_applicator"
CRON = "0 1 * * *"


async def run(session: AsyncSession) -> None:
    now = datetime.now(UTC)
    results = await service.apply_late_fees(session=session, now=now)
    await session.commit()
    log.info(
        "late_fee_applicator.applied",
        extra={"count": len(results), "now": now.isoformat()},
    )


register_job(
    JOB_NAME,
    cron=CRON,
    fn=run,
    description="Apply late fees against overdue invoices via debit notes (daily 1 AM).",
)
