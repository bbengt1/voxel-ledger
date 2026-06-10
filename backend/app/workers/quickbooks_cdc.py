"""QuickBooks CDC drift worker (#317, epic #312, Phase 4a).

Every ~30 minutes, polls QBO's change-data-capture feed for external
edits/deletes to entities we synced and records drift in ``qbo_cdc_drift``.
No-ops entirely unless ``quickbooks.enabled`` and a credential is connected, so
it is safe to register in every environment.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.settings import load_settings
from app.services.quickbooks import cdc
from app.workers.registry import register_job

log = logging.getLogger(__name__)

JOB_NAME = "quickbooks_cdc"
CRON = "*/30 * * * *"


async def run(session: AsyncSession) -> None:
    now = datetime.now(UTC)
    result = await cdc.poll(session, load_settings(), now=now)
    log.info(
        "quickbooks_cdc.done",
        extra={
            "skipped": result.skipped,
            "scanned": result.scanned,
            "matched": result.matched,
            "drift_new": result.drift_new,
            "drift_updated": result.drift_updated,
            "now": now.isoformat(),
        },
    )


register_job(
    JOB_NAME,
    cron=CRON,
    fn=run,
    description=(
        "Poll QBO change-data-capture for external edits/deletes to synced"
        " entities and record drift for admin review (every 30 minutes)."
    ),
)
