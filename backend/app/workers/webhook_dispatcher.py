"""Outbound webhook dispatcher worker (Phase 11.1, #193).

Drains pending ``webhook_delivery`` rows every minute. Each row is
attempted once per tick; retries are scheduled by the dispatcher via
exponential backoff with jitter.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.webhooks import dispatcher
from app.workers.registry import register_job

log = logging.getLogger(__name__)

JOB_NAME = "webhook_dispatcher"
CRON = "* * * * *"


async def run(session: AsyncSession) -> None:
    now = datetime.now(UTC)
    result = await dispatcher.run_pending(session=session, now=now)
    log.info(
        "webhook_dispatcher.done",
        extra={
            "delivered": result.delivered,
            "retried": result.retried,
            "failed": result.failed,
            "dead_lettered": result.dead_lettered,
            "now": now.isoformat(),
        },
    )


register_job(
    JOB_NAME,
    cron=CRON,
    fn=run,
    description=(
        "Drain pending outbound webhook deliveries: sign, POST, classify,"
        " schedule retries (every minute)."
    ),
)
