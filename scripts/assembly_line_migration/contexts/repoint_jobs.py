"""Step 3 — re-point open jobs to a part_id.

Locked decision #5: only **open** (non-terminal) jobs are touched;
completed/cancelled jobs and all historical inventory_transaction rows
are left untouched (epic decision #4). ``product_id`` is kept (nullable)
for audit.

A job maps cleanly to a single part only when it has exactly one plate.
Multi-plate (or zero-plate) open jobs are ambiguous — flagged for review,
not auto-repointed. Idempotent: a job that already has ``part_id`` is
skipped.
"""

from __future__ import annotations

import uuid

from app.models.job import Job, JobState
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from scripts.assembly_line_migration.framework import StepContext, StepResult, register

_OPEN_STATES = (JobState.DRAFT, JobState.QUEUED, JobState.IN_PROGRESS)


@register("repoint_jobs")
async def migrate(ctx: StepContext) -> StepResult:
    res = StepResult(context="repoint_jobs")
    session = ctx.session

    hash_to_part: dict[str, uuid.UUID] = ctx.state.get("hash_to_part", {})
    plate_to_hash: dict[uuid.UUID, str] = ctx.state.get("plate_to_hash", {})

    jobs = list(
        (
            await session.execute(
                select(Job).where(Job.state.in_(_OPEN_STATES)).options(selectinload(Job.plates))
            )
        )
        .scalars()
        .all()
    )
    res.rows_in = len(jobs)

    for job in jobs:
        if job.part_id is not None:
            res.rows_skipped += 1
            continue

        plates = list(job.plates)
        if len(plates) != 1:
            res.review_items.append(
                f"job {job.job_number} ({job.id}) has {len(plates)} plates — "
                "cannot auto-repoint to a single part; resolve manually"
            )
            continue

        h = plate_to_hash.get(plates[0].id)
        part_id = hash_to_part.get(h) if h else None
        if part_id is None:
            res.review_items.append(
                f"job {job.job_number} ({job.id}): no derived part for its plate recipe"
            )
            continue

        if ctx.dry_run:
            res.rows_out += 1
            continue

        # Direct attribute set — part_id is immutable via the jobs service;
        # this is a one-time backfill. product_id is intentionally retained.
        job.part_id = part_id
        await session.flush()
        res.rows_out += 1

    return res
