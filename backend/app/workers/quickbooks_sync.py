"""QuickBooks sync worker (#316, epic #312).

Every ~5 minutes, drains the ``qbo_sync_outbox``: builds + pushes each due
posting to QBO, with backoff + dead-letter. No-ops entirely unless
``quickbooks.enabled`` and a credential is connected, so it is safe to register
in every environment.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.settings import load_settings
from app.services.quickbooks import outbox
from app.workers.registry import register_job

log = logging.getLogger(__name__)

JOB_NAME = "quickbooks_sync"
CRON = "*/5 * * * *"


async def run(session: AsyncSession) -> None:
    now = datetime.now(UTC)
    result = await outbox.run_pending(session, load_settings(), now=now)
    log.info(
        "quickbooks_sync.done",
        extra={
            "skipped": result.skipped,
            "synced": result.synced,
            "retried": result.retried,
            "failed": result.failed,
            "dead": result.dead,
            "now": now.isoformat(),
        },
    )


register_job(
    JOB_NAME,
    cron=CRON,
    fn=run,
    description=(
        "Drain the QBO sync outbox: build + push pending postings to QuickBooks,"
        " backoff on 429, dead-letter on exhaustion (every 5 minutes)."
    ),
)
