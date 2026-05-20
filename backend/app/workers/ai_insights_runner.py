"""AI insights worker (Phase 10.7, #182).

Drains queued ``ai_insight_summary`` rows every 15 minutes. Each row
is processed independently — one failure doesn't block the rest, and
the service commits per row so a mid-run crash doesn't lose work.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.services import ai_insights as service
from app.workers.registry import register_job

log = logging.getLogger(__name__)

JOB_NAME = "ai_insights_runner"
CRON = "*/15 * * * *"


async def run(session: AsyncSession) -> None:
    now = datetime.now(UTC)
    result = await service.run_pending(session=session, now=now)
    log.info(
        "ai_insights_runner.done",
        extra={
            "processed": result.processed,
            "failed": result.failed,
            "now": now.isoformat(),
        },
    )


register_job(
    JOB_NAME,
    cron=CRON,
    fn=run,
    description=(
        "Drain queued AI-insight summary requests, render narratives, mark"
        " rows ready or failed (every 15 min)."
    ),
)
