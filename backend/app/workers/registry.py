"""Minimal worker registry (Phase 1.2 / extended by Phase 7.5).

Workers register themselves with a name + cron expression + async
callable. The process manager (OS cron, k8s CronJob, or an in-process
scheduler in a future phase) looks the job up by name and invokes
``run_job(name)`` which opens a session and runs the coroutine.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

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


async def run_job(name: str, *, session: AsyncSession) -> None:
    job = _REGISTRY.get(name)
    if job is None:
        raise KeyError(f"worker job {name!r} not registered")
    log.info("worker.start", extra={"job": name})
    try:
        await job.fn(session)
    except Exception:
        log.exception("worker.failed", extra={"job": name})
        raise
    log.info("worker.done", extra={"job": name})
