"""Minimal worker registry (Phase 1.2 / extended by Phase 7.5 + #220).

Workers register themselves with a name + cron expression + async
callable. The process manager (OS cron, k8s CronJob, or an in-process
scheduler in a future phase) looks the job up by name and invokes
``run_job(name)`` which opens a session and runs the coroutine.

Since #220 every call to ``run_job`` also writes a
``worker_run_state`` row (status=``running`` on entry,
``ok``/``failed`` on exit, with elapsed ``last_duration_ms`` and the
error message on failure). The state write happens in its OWN
session so a rollback inside the worker doesn't take the run-state
write with it.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from time import perf_counter

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.worker_run_state import WorkerRunState, WorkerRunStatus

log = logging.getLogger(__name__)


JobFn = Callable[[AsyncSession], Awaitable[None]]


@dataclass(frozen=True)
class WorkerJob:
    name: str
    cron: str
    fn: JobFn
    description: str = ""


_REGISTRY: dict[str, WorkerJob] = {}


def register_job(
    name: str,
    *,
    cron: str,
    fn: JobFn,
    description: str = "",
) -> WorkerJob:
    if name in _REGISTRY:
        raise ValueError(f"worker job {name!r} already registered")
    job = WorkerJob(name=name, cron=cron, fn=fn, description=description)
    _REGISTRY[name] = job
    return job


def list_jobs() -> list[WorkerJob]:
    return list(_REGISTRY.values())


# ---------------------------------------------------------------------------
# State persistence (own session, never piggybacks the worker's TX)
# ---------------------------------------------------------------------------


async def _upsert_state(
    *,
    session_factory: async_sessionmaker[AsyncSession] | None,
    job_name: str,
    started_at: datetime | None = None,
    finished_at: datetime | None = None,
    status: WorkerRunStatus | None = None,
    error: str | None = None,
    duration_ms: int | None = None,
    processed: int | None = None,
) -> None:
    """UPSERT a ``worker_run_state`` row. Best-effort: a state-write
    failure must not break the worker run, so we swallow + log."""
    if session_factory is None:
        return
    try:
        async with session_factory() as session:
            existing = (
                await session.execute(
                    select(WorkerRunState).where(WorkerRunState.job_name == job_name)
                )
            ).scalar_one_or_none()
            if existing is None:
                existing = WorkerRunState(job_name=job_name)
                session.add(existing)
            if started_at is not None:
                existing.last_started_at = started_at
            if finished_at is not None:
                existing.last_finished_at = finished_at
            if status is not None:
                existing.last_status = status
            # On success, explicitly clear any stale error string.
            if status == WorkerRunStatus.OK:
                existing.last_error = None
            elif status == WorkerRunStatus.FAILED:
                existing.last_error = error
            if duration_ms is not None:
                existing.last_duration_ms = duration_ms
            if processed is not None:
                existing.last_processed = processed
            await session.commit()
    except Exception:
        log.warning("worker.run_state_write_failed", extra={"job": job_name}, exc_info=True)


# ---------------------------------------------------------------------------
# run_job
# ---------------------------------------------------------------------------


async def run_job(
    name: str,
    *,
    session: AsyncSession,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
) -> None:
    """Run the registered job ``name``.

    ``session`` is the job's own working session (whatever the
    process manager passed in). ``session_factory`` is the
    independent factory used for run-state writes — defaults to
    ``app.core.db._session_factory`` so callers don't have to thread
    it through.
    """
    job = _REGISTRY.get(name)
    if job is None:
        raise KeyError(f"worker job {name!r} not registered")

    if session_factory is None:
        from app.core import db as db_module

        session_factory = db_module._session_factory

    started = datetime.now(UTC)
    started_perf = perf_counter()
    await _upsert_state(
        session_factory=session_factory,
        job_name=name,
        started_at=started,
        status=WorkerRunStatus.RUNNING,
    )
    log.info("worker.start", extra={"job": name})
    try:
        await job.fn(session)
    except Exception as exc:
        duration_ms = int((perf_counter() - started_perf) * 1000)
        log.exception("worker.failed", extra={"job": name})
        await _upsert_state(
            session_factory=session_factory,
            job_name=name,
            finished_at=datetime.now(UTC),
            status=WorkerRunStatus.FAILED,
            error=str(exc) or exc.__class__.__name__,
            duration_ms=duration_ms,
        )
        raise
    duration_ms = int((perf_counter() - started_perf) * 1000)
    await _upsert_state(
        session_factory=session_factory,
        job_name=name,
        finished_at=datetime.now(UTC),
        status=WorkerRunStatus.OK,
        duration_ms=duration_ms,
    )
    log.info("worker.done", extra={"job": name})


__all__ = [
    "JobFn",
    "WorkerJob",
    "list_jobs",
    "register_job",
    "run_job",
]
