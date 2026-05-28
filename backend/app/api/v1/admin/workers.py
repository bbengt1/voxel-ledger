"""Admin endpoint for worker run-state (Issue #220).

Lists the durable per-job state recorded by ``app/workers/registry.run_job``:
last start, last finish, status, duration, error. Owner-only.

Used by ops to answer "did this cron run? when last? did it fail?"
without diving into container logs.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_role
from app.core.db import get_session
from app.models.auth import User
from app.models.worker_run_state import WorkerRunState
from app.schemas.workers import WorkerRunStateRead
from app.workers.registry import list_jobs

router = APIRouter(prefix="/workers", tags=["admin-workers"])


@router.get("", response_model=list[WorkerRunStateRead])
async def list_worker_states(
    session: Annotated[AsyncSession, Depends(get_session)],
    _user: Annotated[User, Depends(require_role("owner", "bookkeeper"))],
) -> list[WorkerRunStateRead]:
    """Return one row per registered worker, including jobs that have
    never run (status=null). Sorted by job name for stable display."""
    rows = (await session.execute(select(WorkerRunState))).scalars().all()
    state_by_name = {row.job_name: row for row in rows}

    out: list[WorkerRunStateRead] = []
    for job in sorted(list_jobs(), key=lambda j: j.name):
        state = state_by_name.get(job.name)
        out.append(
            WorkerRunStateRead(
                job_name=job.name,
                cron=job.cron,
                description=job.description,
                last_started_at=state.last_started_at if state else None,
                last_finished_at=state.last_finished_at if state else None,
                last_status=(
                    state.last_status.value if state and state.last_status is not None else None
                ),
                last_error=state.last_error if state else None,
                last_processed=state.last_processed if state else 0,
                last_duration_ms=state.last_duration_ms if state else None,
                updated_at=state.updated_at if state else None,
            )
        )
    return out
