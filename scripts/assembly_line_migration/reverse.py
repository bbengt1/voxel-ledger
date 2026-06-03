"""Scripted inverse of the assembly-line backfill (epic #267, Phase 7a).

Cleanly undoes a *commit* run for a "clean but wrong" outcome, without
restoring a backup. Because the engine is non-destructive (it never
deleted existing data — material lines were only flagged), the inverse
is exact:

  1. null ``job.part_id`` on jobs pointing at a migration-origin part
     (``product_id`` is restored as the sole target);
  2. delete product→part BOM lines referencing migration-origin parts;
  3. delete the migration-origin Parts themselves.

Dry-run (default) rolls back. A corrupt run (not clean) should instead
be recovered from the pre-cutover ``pg_dump`` per the 7b runbook.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from app.models.job import Job
from app.models.part import Part
from app.models.product_bom_item import COMPONENT_KIND_PART, ProductBomItem
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from scripts.assembly_line_migration.recipe import ORIGIN_KEY, ORIGIN_VALUE

log = logging.getLogger(__name__)


@dataclass
class ReverseResult:
    dry_run: bool
    parts_found: int = 0
    jobs_unpointed: int = 0
    bom_lines_deleted: int = 0
    parts_deleted: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def summary(self) -> str:
        return (
            f"assembly-line REVERSE {'(DRY-RUN)' if self.dry_run else '(COMMIT)'} "
            f"status={'ok' if self.ok else 'FAILED'} "
            f"parts_found={self.parts_found} jobs_unpointed={self.jobs_unpointed} "
            f"bom_lines_deleted={self.bom_lines_deleted} parts_deleted={self.parts_deleted}"
        )


async def reverse_all(*, session: AsyncSession, dry_run: bool = True) -> ReverseResult:
    res = ReverseResult(dry_run=dry_run)

    parts = list((await session.execute(select(Part))).scalars().all())
    migration_part_ids: list[uuid.UUID] = [
        p.id for p in parts if (p.custom_fields or {}).get(ORIGIN_KEY) == ORIGIN_VALUE
    ]
    res.parts_found = len(migration_part_ids)
    if not migration_part_ids:
        return res

    # 1) un-point jobs.
    jobs = list(
        (await session.execute(select(Job).where(Job.part_id.in_(migration_part_ids))))
        .scalars()
        .all()
    )
    res.jobs_unpointed = len(jobs)

    # 2) part BOM lines referencing migration parts.
    bom_lines = list(
        (
            await session.execute(
                select(ProductBomItem.id).where(
                    ProductBomItem.component_kind == COMPONENT_KIND_PART,
                    ProductBomItem.component_id.in_(migration_part_ids),
                )
            )
        )
        .scalars()
        .all()
    )
    res.bom_lines_deleted = len(bom_lines)
    res.parts_deleted = len(migration_part_ids)

    if dry_run:
        await session.rollback()
        started = datetime.now(UTC)
        log.info("assembly_line_reverse.dry_run", extra={"at": started.isoformat()})
        return res

    if jobs:
        await session.execute(
            update(Job).where(Job.part_id.in_(migration_part_ids)).values(part_id=None)
        )
    if bom_lines:
        await session.execute(delete(ProductBomItem).where(ProductBomItem.id.in_(bom_lines)))
    await session.execute(delete(Part).where(Part.id.in_(migration_part_ids)))
    await session.commit()
    return res


__all__ = ["ReverseResult", "reverse_all"]
