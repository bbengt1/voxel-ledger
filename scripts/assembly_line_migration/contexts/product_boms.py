"""Step 2 — build product→part BOM lines from historical jobs.

Locked decisions:
  #2 map each distinct plate on a product's jobs to **one part BOM line
     at qty 1**; never guess multi-up ratios. Products whose jobs imply
     *different* part sets are flagged for review (not auto-resolved).
  #3 legacy direct-``material`` product BOM lines: a line whose material
     is covered by one of the product's parts is flagged "safe to remove
     (now part-mediated)"; an uncovered line is flagged "needs manual
     handling". **Neither is auto-deleted** — the engine stays
     non-destructive + reversible; removal is a reviewed follow-up.

Idempotent on ``(product, part)``: an existing part BOM line is skipped.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from app.models.job import Job
from app.models.product_bom_item import (
    COMPONENT_KIND_MATERIAL,
    COMPONENT_KIND_PART,
    ProductBomItem,
)
from app.services import bom as bom_service
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from scripts.assembly_line_migration.framework import StepContext, StepResult, register


@register("product_boms")
async def migrate(ctx: StepContext) -> StepResult:
    res = StepResult(context="product_boms")
    session = ctx.session

    hash_to_part: dict[str, uuid.UUID] = ctx.state.get("hash_to_part", {})
    plate_to_hash: dict[uuid.UUID, str] = ctx.state.get("plate_to_hash", {})

    jobs = list(
        (
            await session.execute(
                select(Job).where(Job.product_id.isnot(None)).options(selectinload(Job.plates))
            )
        )
        .scalars()
        .all()
    )

    # product → union of part ids; product → set of materials its plates use;
    # product → set of per-job part-id frozensets (to detect inconsistency).
    product_parts: dict[uuid.UUID, set[uuid.UUID]] = {}
    product_plate_materials: dict[uuid.UUID, set[uuid.UUID]] = {}
    product_job_sets: dict[uuid.UUID, set[frozenset[uuid.UUID]]] = {}

    for job in jobs:
        pid = job.product_id
        assert pid is not None
        job_parts: set[uuid.UUID] = set()
        for plate in job.plates:
            h = plate_to_hash.get(plate.id)
            part_id = hash_to_part.get(h) if h else None
            if part_id is not None:
                job_parts.add(part_id)
            for mat_key in plate.print_grams_by_material or {}:
                product_plate_materials.setdefault(pid, set()).add(uuid.UUID(str(mat_key)))
        product_parts.setdefault(pid, set()).update(job_parts)
        if job_parts:
            product_job_sets.setdefault(pid, set()).add(frozenset(job_parts))

    res.rows_in = len(product_parts)

    # Pre-load existing part BOM lines for idempotency.
    existing_part_lines = set(
        (
            await session.execute(
                select(ProductBomItem.parent_product_id, ProductBomItem.component_id).where(
                    ProductBomItem.component_kind == COMPONENT_KIND_PART
                )
            )
        ).all()
    )

    for pid, part_ids in product_parts.items():
        # Inconsistency review (decision #2): jobs disagree on the part set.
        sets = product_job_sets.get(pid, set())
        if len(sets) > 1:
            res.review_items.append(
                f"product {pid}: jobs imply differing part sets "
                f"({[sorted(str(x) for x in s) for s in sets]}) — verify BOM"
            )

        for part_id in sorted(part_ids, key=str):
            if (pid, part_id) in existing_part_lines:
                res.rows_skipped += 1
                continue
            if ctx.dry_run:
                res.rows_out += 1
                continue
            await bom_service.add_component(
                session,
                parent_product_id=pid,
                component_kind=COMPONENT_KIND_PART,
                component_id=part_id,
                quantity=Decimal("1"),
                notes="assembly-line backfill (Phase 7a): 1 part/plate",
                actor_user_id=ctx.actor_user_id,
            )
            existing_part_lines.add((pid, part_id))
            res.rows_out += 1

    # Material-line handling (decision #3) — flag, never delete.
    material_lines = list(
        (
            await session.execute(
                select(ProductBomItem).where(
                    ProductBomItem.component_kind == COMPONENT_KIND_MATERIAL
                )
            )
        )
        .scalars()
        .all()
    )
    for line in material_lines:
        pid = line.parent_product_id
        covered = line.component_id in product_plate_materials.get(pid, set())
        if covered:
            res.review_items.append(
                f"product {pid}: direct material line {line.component_id} is covered by "
                f"its part(s) — safe to remove (now part-mediated)"
            )
        else:
            res.review_items.append(
                f"product {pid}: direct material line {line.component_id} is NOT covered by "
                f"any derived part — needs manual handling"
            )

    return res
