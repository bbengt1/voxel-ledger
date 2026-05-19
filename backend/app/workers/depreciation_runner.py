"""Depreciation run worker (Phase 9.3, #155).

Runs at 02:00 on the 1st of every month (``cron('0 2 1 * *')``).
Depreciates the calendar month that just ended: ``period_end =`` last
day of the prior month. Calls
:func:`app.services.depreciation_run.run_for_period`, which posts a
balanced JE per planned schedule entry and flips its state to
``posted``.

The service commits inside its own loop (one commit per entry), so the
worker only needs to call it and log the totals.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.services import depreciation_run as service
from app.workers.registry import register_job

log = logging.getLogger(__name__)

JOB_NAME = "depreciation_runner"
CRON = "0 2 1 * *"


async def run(session: AsyncSession) -> None:
    now = datetime.now(UTC)
    period_end = service.previous_month_end(now)
    result = await service.run_for_period(session=session, period_end=period_end)
    log.info(
        "depreciation_runner.done",
        extra={
            "period_end": result.period_end.isoformat(),
            "posted_count": result.posted_count,
            "failed_count": result.failed_count,
            "now": now.isoformat(),
        },
    )


register_job(
    JOB_NAME,
    cron=CRON,
    fn=run,
    description=(
        "Sweep planned depreciation entries for the prior month and post JEs "
        "(monthly 2 AM on the 1st)."
    ),
)
