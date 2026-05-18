"""Bank auto-match worker (Phase 8.10, #137).

Runs every 15 minutes (``cron('*/15 * * * *')``). Calls
``bank_auto_matcher.run_once`` to apply every active match rule against
the current pool of ``state=unmatched`` ``bank_transaction`` rows, then
commits.

Per-template exceptions are swallowed inside ``run_once`` so the worker
keeps going on bad rules.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.services import bank_auto_matcher as service
from app.workers.registry import register_job

log = logging.getLogger(__name__)

JOB_NAME = "bank_auto_matcher"
CRON = "*/15 * * * *"


async def run(session: AsyncSession) -> None:
    """Worker entrypoint: auto-match all currently-unmatched rows."""
    now = datetime.now(UTC)
    results = await service.run_once(session=session, now=now)
    await session.commit()
    by_action: dict[str, int] = {}
    for r in results:
        by_action[r.action_kind] = by_action.get(r.action_kind, 0) + 1
    log.info(
        "bank_auto_matcher.applied",
        extra={
            "count": len(results),
            "by_action": by_action,
            "now": now.isoformat(),
        },
    )


register_job(
    JOB_NAME,
    cron=CRON,
    fn=run,
    description="Auto-match unmatched bank transactions against active match rules (every 15 min).",
)
