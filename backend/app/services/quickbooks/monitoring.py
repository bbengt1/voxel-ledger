"""QBO sync monitoring metrics (#317 Phase 4d, epic #312).

A cheap, alert-friendly snapshot of sync health: worker freshness (when the
sync/CDC workers last finished + their status — the *sync lag* signal), the
outbox queue depths (pending/failed/**dead**), how long the oldest pending row
has been waiting, and the open-drift count. Mirrors the existing worker-state
monitoring (``GET /admin/workers``) but folds in the queue + drift depths that
run-state alone doesn't capture, so ops can probe one endpoint for sync lag and
dead-letter/drift without running the heavy reconciliation report.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.qbo_sync_outbox import QboSyncOutbox, QboSyncStatus
from app.models.worker_run_state import WorkerRunState
from app.services.quickbooks import cdc, oauth, outbox
from app.workers.quickbooks_cdc import JOB_NAME as CDC_JOB
from app.workers.quickbooks_sync import JOB_NAME as SYNC_JOB


@dataclass(frozen=True)
class WorkerHealth:
    job_name: str
    last_finished_at: datetime | None
    last_status: str | None
    last_duration_ms: int | None
    last_processed: int


@dataclass(frozen=True)
class SyncMetrics:
    enabled: bool
    connected: bool
    outbox: dict[str, int]
    drift_open: int
    oldest_pending_age_seconds: int | None
    sync_worker: WorkerHealth
    cdc_worker: WorkerHealth


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


async def _worker_health(session: AsyncSession, job_name: str) -> WorkerHealth:
    row = await session.get(WorkerRunState, job_name)
    if row is None:
        return WorkerHealth(job_name, None, None, None, 0)
    return WorkerHealth(
        job_name=job_name,
        last_finished_at=row.last_finished_at,
        last_status=(row.last_status.value if row.last_status is not None else None),
        last_duration_ms=row.last_duration_ms,
        last_processed=row.last_processed or 0,
    )


async def _oldest_pending_age_seconds(session: AsyncSession, now: datetime) -> int | None:
    """Age (s) of the oldest still-pending outbox row — the backlog/lag signal."""
    oldest = (
        await session.execute(
            select(func.min(QboSyncOutbox.created_at)).where(
                QboSyncOutbox.status == QboSyncStatus.PENDING.value
            )
        )
    ).scalar_one_or_none()
    if oldest is None:
        return None
    return max(0, int((now - _as_utc(oldest)).total_seconds()))


async def build_metrics(session: AsyncSession, *, now: datetime | None = None) -> SyncMetrics:
    """Snapshot the sync queue + worker freshness for monitoring/alerting."""
    now = now or datetime.now(UTC)
    return SyncMetrics(
        enabled=await outbox.is_enabled(session),
        connected=await oauth.get_credential(session) is not None,
        outbox=await outbox.stats(session),
        drift_open=await cdc.open_drift_count(session),
        oldest_pending_age_seconds=await _oldest_pending_age_seconds(session, now),
        sync_worker=await _worker_health(session, SYNC_JOB),
        cdc_worker=await _worker_health(session, CDC_JOB),
    )
