"""Step 1 — derive deduped Parts from historical plate recipes.

Locked decisions:
  #1 dedupe by **exact recipe hash** (one Part per distinct recipe);
     ``name`` from the most-common source plate.
  #4 SKU scheme ``PART-MIG-NNNN``.

Idempotent: a recipe whose hash is already stamped on an existing Part
(in ``custom_fields.migration_recipe_hash``) is skipped. Publishes the
``hash → part_id`` map and the per-plate ``plate_id → hash`` map into
``ctx.state`` for the downstream steps.
"""

from __future__ import annotations

import uuid
from collections import Counter
from decimal import Decimal

from app.models.part import Part
from app.models.plate import Plate
from app.services import parts as parts_service
from sqlalchemy import select

from scripts.assembly_line_migration.framework import StepContext, StepResult, register
from scripts.assembly_line_migration.recipe import (
    ORIGIN_KEY,
    ORIGIN_VALUE,
    RECIPE_HASH_KEY,
    placeholder_part_id,
    plate_recipe_hash,
)


@register("derive_parts")
async def migrate(ctx: StepContext) -> StepResult:
    res = StepResult(context="derive_parts")
    session = ctx.session

    plates = list((await session.execute(select(Plate))).scalars().all())
    res.rows_in = len(plates)

    # Existing parts: build hash → id (idempotency) + find the max
    # PART-MIG-NNNN sequence so we keep numbering monotonic.
    existing = list((await session.execute(select(Part))).scalars().all())
    hash_to_part: dict[str, uuid.UUID] = {}
    max_seq = 0
    for p in existing:
        cf = p.custom_fields or {}
        h = cf.get(RECIPE_HASH_KEY)
        if isinstance(h, str):
            hash_to_part[h] = p.id
        if p.sku.startswith("PART-MIG-"):
            tail = p.sku.rsplit("-", 1)[-1]
            if tail.isdigit():
                max_seq = max(max_seq, int(tail))

    # Group plates by recipe hash; pick the most-common name per group.
    plates_by_hash: dict[str, list[Plate]] = {}
    plate_to_hash: dict[uuid.UUID, str] = {}
    for pl in plates:
        h = plate_recipe_hash(pl)
        plate_to_hash[pl.id] = h
        plates_by_hash.setdefault(h, []).append(pl)

    seq = max_seq
    for h, group in plates_by_hash.items():
        if h in hash_to_part:
            res.rows_skipped += 1
            continue

        name = Counter([(g.name or "").strip() or "part" for g in group]).most_common(1)[0][0]
        sample = group[0]

        if ctx.dry_run:
            # Plan only — hand downstream a deterministic placeholder id.
            hash_to_part[h] = placeholder_part_id(h)
            res.rows_out += 1
            continue

        seq += 1
        sku = f"PART-MIG-{seq:04d}"
        grams = {
            uuid.UUID(str(k)): Decimal(str(v))
            for k, v in (sample.print_grams_by_material or {}).items()
        }
        printers = [uuid.UUID(str(p)) for p in (sample.assigned_printer_ids or [])]
        part = await parts_service.create(
            session,
            name=name,
            sku=sku,
            print_minutes=sample.print_minutes,
            setup_minutes=sample.print_hours_setup_minutes,
            parts_per_run=sample.parts_per_set,
            print_grams_by_material=grams,
            assigned_printer_ids=printers,
            custom_fields={RECIPE_HASH_KEY: h, ORIGIN_KEY: ORIGIN_VALUE},
            actor_user_id=ctx.actor_user_id,
        )
        hash_to_part[h] = part.id
        res.rows_out += 1

    ctx.state["hash_to_part"] = hash_to_part
    ctx.state["plate_to_hash"] = plate_to_hash
    return res
