"""Recurring bill materializer worker (Phase 8.5, #132).

Runs every 15 minutes (``cron('*/15 * * * *')``). AP-side mirror of the
recurring-invoice materializer. Scans active ``recurring_bill_template``
rows whose ``next_issue_at <= now()`` and materializes a draft bill
(auto-issued bill if ``auto_issue=True``) for each. The service layer's
``next_issue_at`` advance gates idempotency.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.services import recurring_bills as service
from app.workers.registry import register_job

log = logging.getLogger(__name__)

JOB_NAME = "recurring_bill_materializer"
CRON = "*/15 * * * *"


async def run(session: AsyncSession) -> None:
    """Worker entrypoint: materialize all currently-due templates."""
    now = datetime.now(UTC)
    created = await service.materialize_due(session=session, now=now)
    await session.commit()
    log.info(
        "recurring_bill_materializer.materialized",
        extra={"count": len(created), "now": now.isoformat()},
    )


register_job(
    JOB_NAME,
    cron=CRON,
    fn=run,
    description="Materialize draft bills from due recurring templates (every 15 min).",
)
