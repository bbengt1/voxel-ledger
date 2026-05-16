"""Recurring invoice materializer worker (Phase 7.5, #113).

Runs every 15 minutes (``cron('*/15 * * * *')``). Scans for active
``recurring_invoice_template`` rows whose ``next_issue_at <= now()`` and
materializes a draft invoice (or auto-issued invoice if ``auto_issue=True``)
for each. The service layer's ``next_issue_at`` advance gates idempotency.

The job exposes one entrypoint, ``run(session)``, so the registry can call
into it with a fresh session. Per-template exceptions are swallowed inside
``materialize_due`` so the worker keeps going on bad rows.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.services import recurring_invoices as service
from app.workers.registry import register_job

log = logging.getLogger(__name__)

JOB_NAME = "recurring_invoice_materializer"
CRON = "*/15 * * * *"


async def run(session: AsyncSession) -> None:
    """Worker entrypoint: materialize all currently-due templates."""
    now = datetime.now(UTC)
    created = await service.materialize_due(session=session, now=now)
    await session.commit()
    log.info(
        "recurring_invoice_materializer.materialized",
        extra={"count": len(created), "now": now.isoformat()},
    )


register_job(
    JOB_NAME,
    cron=CRON,
    fn=run,
    description="Materialize draft invoices from due recurring templates (every 15 min).",
)
