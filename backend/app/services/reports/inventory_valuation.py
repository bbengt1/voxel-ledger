"""Inventory valuation report (Phase 10.5, #180).

Snapshot of on-hand times cost-per-unit as of a date. Reads
``inventory_on_hand`` (Phase 3.3 projection) and joins each row to the
catalog table for its ``entity_kind`` to pull the unit cost:

* ``material.current_cost_per_gram``
* ``supply.unit_cost``
* ``product.unit_cost_cached`` (nullable — null cost yields a zero
  valuation row so the operator can spot un-rolled-up BOMs)

The ``inventory_on_hand`` table is a running projection and doesn't
store historical balances, so ``as_of`` only filters the catalog cost
lookup forward — historical valuations need the inventory-ledger
replay (Phase 3.x). For #10.5 we report "right now" + ``location_id``
filtering, which is the common bookkeeper question.
"""

from __future__ import annotations

import io
import uuid
from csv import writer as csv_writer
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.inventory_location import InventoryLocation
from app.models.inventory_on_hand import InventoryOnHand
from app.models.inventory_transaction import (
    ENTITY_KIND_MATERIAL,
    ENTITY_KIND_PRODUCT,
    ENTITY_KIND_SUPPLY,
)
from app.models.material import Material
from app.models.product import Product
from app.models.supply import Supply

_QUANTUM = Decimal("0.01")
_ZERO = Decimal("0")


def _q(value: Decimal) -> Decimal:
    return value.quantize(_QUANTUM, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class InventoryValuationRow:
    entity_kind: str
    entity_id: str
    name: str
    sku: str | None
    location_id: str
    location_name: str
    on_hand: Decimal
    unit_cost: Decimal
    valuation: Decimal


@dataclass(frozen=True)
class InventoryValuationReport:
    as_of: date
    location_id: str | None
    rows: list[InventoryValuationRow]
    total_valuation: Decimal
    totals_by_kind: dict[str, Decimal]
    totals_by_location: dict[str, Decimal]


async def _load_locations(
    session: AsyncSession, ids: set[uuid.UUID]
) -> dict[uuid.UUID, InventoryLocation]:
    if not ids:
        return {}
    rows = (
        (await session.execute(select(InventoryLocation).where(InventoryLocation.id.in_(ids))))
        .scalars()
        .all()
    )
    return {row.id: row for row in rows}


async def _load_costs(
    session: AsyncSession,
    *,
    materials: set[uuid.UUID],
    supplies: set[uuid.UUID],
    products: set[uuid.UUID],
) -> tuple[
    dict[uuid.UUID, tuple[str, str | None, Decimal]],
    dict[uuid.UUID, tuple[str, str | None, Decimal]],
    dict[uuid.UUID, tuple[str, str | None, Decimal]],
]:
    """Return per-kind dicts of ``{id: (name, sku, unit_cost)}``."""
    out_m: dict[uuid.UUID, tuple[str, str | None, Decimal]] = {}
    out_s: dict[uuid.UUID, tuple[str, str | None, Decimal]] = {}
    out_p: dict[uuid.UUID, tuple[str, str | None, Decimal]] = {}

    if materials:
        for m in (
            (await session.execute(select(Material).where(Material.id.in_(materials))))
            .scalars()
            .all()
        ):
            out_m[m.id] = (
                m.name,
                getattr(m, "sku", None),
                Decimal(str(m.current_cost_per_gram or 0)),
            )
    if supplies:
        for s in (
            (await session.execute(select(Supply).where(Supply.id.in_(supplies)))).scalars().all()
        ):
            out_s[s.id] = (
                s.name,
                getattr(s, "sku", None),
                Decimal(str(s.unit_cost or 0)),
            )
    if products:
        for p in (
            (await session.execute(select(Product).where(Product.id.in_(products)))).scalars().all()
        ):
            out_p[p.id] = (
                getattr(p, "name", ""),
                getattr(p, "sku", None),
                Decimal(str(p.unit_cost_cached or 0)),
            )
    return out_m, out_s, out_p


async def build(
    session: AsyncSession,
    *,
    as_of: date | None = None,
    location_id: uuid.UUID | str | None = None,
) -> InventoryValuationReport:
    if as_of is None:
        as_of = datetime.now(UTC).date()

    location_uuid: uuid.UUID | None = None
    if location_id is not None:
        location_uuid = (
            location_id if isinstance(location_id, uuid.UUID) else uuid.UUID(str(location_id))
        )

    stmt = select(InventoryOnHand).where(InventoryOnHand.on_hand != 0)
    if location_uuid is not None:
        stmt = stmt.where(InventoryOnHand.location_id == location_uuid)
    on_hand_rows = list((await session.execute(stmt)).scalars().all())

    materials = {r.entity_id for r in on_hand_rows if r.entity_kind == ENTITY_KIND_MATERIAL}
    supplies = {r.entity_id for r in on_hand_rows if r.entity_kind == ENTITY_KIND_SUPPLY}
    products = {r.entity_id for r in on_hand_rows if r.entity_kind == ENTITY_KIND_PRODUCT}
    out_m, out_s, out_p = await _load_costs(
        session,
        materials=materials,
        supplies=supplies,
        products=products,
    )

    location_ids = {r.location_id for r in on_hand_rows}
    locations = await _load_locations(session, location_ids)

    rows: list[InventoryValuationRow] = []
    totals_by_kind: dict[str, Decimal] = {}
    totals_by_location: dict[str, Decimal] = {}
    total = _ZERO

    for row in on_hand_rows:
        kind = row.entity_kind
        if kind == ENTITY_KIND_MATERIAL:
            meta = out_m.get(row.entity_id)
        elif kind == ENTITY_KIND_SUPPLY:
            meta = out_s.get(row.entity_id)
        elif kind == ENTITY_KIND_PRODUCT:
            meta = out_p.get(row.entity_id)
        else:
            continue
        if meta is None:
            # Catalog row was deleted; surface a stub row at zero cost.
            name = f"({kind} {row.entity_id})"
            sku = None
            unit_cost = _ZERO
        else:
            name, sku, unit_cost = meta

        on_hand = Decimal(str(row.on_hand))
        valuation = _q(on_hand * unit_cost)

        loc = locations.get(row.location_id)
        loc_name = loc.name if loc is not None else str(row.location_id)

        rows.append(
            InventoryValuationRow(
                entity_kind=kind,
                entity_id=str(row.entity_id),
                name=name,
                sku=sku,
                location_id=str(row.location_id),
                location_name=loc_name,
                on_hand=on_hand,
                unit_cost=unit_cost,
                valuation=valuation,
            )
        )
        total += valuation
        totals_by_kind[kind] = _q(totals_by_kind.get(kind, _ZERO) + valuation)
        totals_by_location[str(row.location_id)] = _q(
            totals_by_location.get(str(row.location_id), _ZERO) + valuation
        )

    rows.sort(key=lambda r: (r.location_name, r.entity_kind, r.name))

    return InventoryValuationReport(
        as_of=as_of,
        location_id=str(location_uuid) if location_uuid is not None else None,
        rows=rows,
        total_valuation=_q(total),
        totals_by_kind=totals_by_kind,
        totals_by_location=totals_by_location,
    )


def to_csv(report: InventoryValuationReport) -> str:
    buf = io.StringIO()
    w = csv_writer(buf)
    w.writerow(
        [
            "location",
            "entity_kind",
            "sku",
            "name",
            "on_hand",
            "unit_cost",
            "valuation",
        ]
    )
    for r in report.rows:
        w.writerow(
            [
                r.location_name,
                r.entity_kind,
                r.sku or "",
                r.name,
                str(r.on_hand),
                str(r.unit_cost),
                str(r.valuation),
            ]
        )
    w.writerow(["GRAND TOTAL", "", "", "", "", "", str(report.total_valuation)])
    return buf.getvalue()


__all__ = [
    "InventoryValuationReport",
    "InventoryValuationRow",
    "build",
    "to_csv",
]
