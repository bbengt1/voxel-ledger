"""Reconciliation: prove the backfill produced a consistent model
(epic #267, Phase 7b).

Flow (run on a restored prod snapshot, then on prod during cutover):

    capture baseline  →  run backfill --commit  →  reconcile vs baseline

Invariants (locked decisions):
  * **On-hand parity (HARD)** — the backfill writes NO inventory
    transactions, so every ``inventory_on_hand`` balance must be
    byte-identical before/after. Any drift is a hard failure → non-zero
    exit → cutover aborts.
  * **Cost parity (SOFT, ±$0.01)** — product ``unit_cost_cached`` is
    expected to move as direct-material lines become part-mediated;
    moves beyond a cent are surfaced for human sign-off, not blocked.
  * **Coverage (SOFT)** — open single-plate jobs that weren't re-pointed
    and products with historical jobs but no part BOM are listed so the
    operator can work them (alongside the backfill's own review list).

``ReconciliationReport.ok`` is true iff there are no hard failures.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any

from app.models.inventory_on_hand import InventoryOnHand
from app.models.job import Job, JobState
from app.models.product import Product
from app.models.product_bom_item import COMPONENT_KIND_PART, ProductBomItem
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

_COST_TOLERANCE = Decimal("0.01")
_OPEN_STATES = (JobState.DRAFT, JobState.QUEUED, JobState.IN_PROGRESS)


# ---------------------------------------------------------------------------
# Baseline
# ---------------------------------------------------------------------------


@dataclass
class Baseline:
    """A pre-backfill snapshot of the invariant-bearing state."""

    on_hand: dict[str, str] = field(default_factory=dict)  # "kind:entity:loc" -> qty
    product_costs: dict[str, str | None] = field(default_factory=dict)  # product_id -> cost

    def to_dict(self) -> dict[str, Any]:
        return {"on_hand": self.on_hand, "product_costs": self.product_costs}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Baseline:
        return cls(
            on_hand=dict(d.get("on_hand", {})),
            product_costs=dict(d.get("product_costs", {})),
        )

    def write(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2))

    @classmethod
    def read(cls, path: Path) -> Baseline:
        return cls.from_dict(json.loads(path.read_text()))


def _onhand_key(kind: str, entity_id: uuid.UUID, location_id: uuid.UUID) -> str:
    return f"{kind}:{entity_id}:{location_id}"


async def capture(session: AsyncSession) -> Baseline:
    rows = list((await session.execute(select(InventoryOnHand))).scalars().all())
    on_hand = {
        _onhand_key(r.entity_kind, r.entity_id, r.location_id): str(Decimal(str(r.on_hand)))
        for r in rows
    }
    products = list((await session.execute(select(Product))).scalars().all())
    product_costs = {
        str(p.id): (str(p.unit_cost_cached) if p.unit_cost_cached is not None else None)
        for p in products
    }
    return Baseline(on_hand=on_hand, product_costs=product_costs)


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


@dataclass
class ReconciliationReport:
    hard_failures: list[str] = field(default_factory=list)
    cost_diffs: list[str] = field(default_factory=list)
    coverage: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.hard_failures

    def summary(self) -> str:
        lines = [
            f"reconciliation status={'PASS' if self.ok else 'FAIL (cutover blocked)'} "
            f"hard_failures={len(self.hard_failures)} "
            f"cost_diffs={len(self.cost_diffs)} coverage={len(self.coverage)}"
        ]
        for h in self.hard_failures:
            lines.append(f"  [HARD]  {h}")
        for c in self.cost_diffs:
            lines.append(f"  [cost]  {c}")
        for c in self.coverage:
            lines.append(f"  [cover] {c}")
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self) | {"ok": self.ok}


async def reconcile(session: AsyncSession, baseline: Baseline) -> ReconciliationReport:
    report = ReconciliationReport()

    # --- On-hand parity (HARD): the backfill must not move any stock. ---
    current = await capture(session)
    base_keys = set(baseline.on_hand)
    cur_keys = set(current.on_hand)
    for key in sorted(base_keys - cur_keys):
        report.hard_failures.append(f"on-hand row vanished after backfill: {key}")
    for key in sorted(cur_keys - base_keys):
        report.hard_failures.append(f"unexpected new on-hand row after backfill: {key}")
    for key in sorted(base_keys & cur_keys):
        if Decimal(baseline.on_hand[key]) != Decimal(current.on_hand[key]):
            report.hard_failures.append(
                f"on-hand changed for {key}: {baseline.on_hand[key]} -> {current.on_hand[key]}"
            )

    # --- Cost parity (SOFT, +/- $0.01). ---
    for pid, before in baseline.product_costs.items():
        after = current.product_costs.get(pid)
        if before is None and after is None:
            continue
        if before is None or after is None:
            report.cost_diffs.append(f"product {pid}: cost {before} -> {after}")
            continue
        if abs(Decimal(after) - Decimal(before)) > _COST_TOLERANCE:
            report.cost_diffs.append(
                f"product {pid}: cost {before} -> {after} "
                f"(delta {Decimal(after) - Decimal(before)})"
            )

    # --- Coverage (SOFT). ---
    open_jobs = list(
        (await session.execute(select(Job).where(Job.state.in_(_OPEN_STATES)))).scalars().all()
    )
    for job in open_jobs:
        if job.part_id is None and job.product_id is not None:
            report.coverage.append(f"open job {job.job_number} ({job.id}) still has no part_id")

    products_with_part_bom = set(
        (
            await session.execute(
                select(ProductBomItem.parent_product_id).where(
                    ProductBomItem.component_kind == COMPONENT_KIND_PART
                )
            )
        )
        .scalars()
        .all()
    )
    products_with_jobs = set(
        (await session.execute(select(Job.product_id).where(Job.product_id.isnot(None))))
        .scalars()
        .all()
    )
    for pid in sorted(products_with_jobs - products_with_part_bom, key=str):
        report.coverage.append(f"product {pid} has historical jobs but no part BOM line")

    return report


__all__ = ["Baseline", "ReconciliationReport", "capture", "reconcile"]
