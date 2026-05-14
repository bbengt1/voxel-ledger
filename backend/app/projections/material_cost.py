"""Projection: weighted-average cost-per-gram.

Subscribes to ``inventory.MaterialReceived``. Recomputes the parent
material's ``current_cost_per_gram`` using a running weighted average:

    new_cost = (old_on_hand * old_cost + receipt_grams * receipt_unit_cost)
               / (old_on_hand + receipt_grams)

Edge: if ``old_on_hand == 0`` the formula reduces to
``new_cost = receipt_unit_cost`` directly.

Phase 3.3 refactor (#52)
------------------------
This projection used to maintain BOTH ``current_cost_per_gram`` AND
``on_hand_grams`` directly on the ``material`` row. ``on_hand_grams``
is gone — per-location balances live in ``inventory_on_hand``,
maintained by the separate ``inventory_on_hand`` projection that
consumes ``inventory.TransactionRecorded``.

The receipts service in Phase 3.3 appends ``inventory.TransactionRecorded``
BEFORE ``inventory.MaterialReceived``, so by the time this handler
fires the new receipt's quantity is already in ``inventory_on_hand``.
We recover ``old_on_hand`` by subtracting this receipt's grams from the
current cross-location sum — the result is the prior balance. Replay
walks events in the same position order, preserving parity.

Decimal arithmetic only — no floats anywhere on the math path. The
final cost is quantized to 6 decimal places, matching the
``Numeric(18, 6)`` column precision.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.events.types.inventory import TYPE_MATERIAL_RECEIVED
from app.models.event import Event
from app.models.inventory_on_hand import InventoryOnHand
from app.models.material import Material
from app.projections.registry import projection

HANDLER_NAME = "material_cost_projection"
READ_MODEL_TABLES: tuple[str, ...] = ("material",)

# Quantize to 6 decimal places at the end of every recompute. Matches
# the Numeric(18, 6) column precision.
_QUANTUM = Decimal("0.000001")


def _to_decimal(value: object) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


async def _sum_on_hand_for_material(session: AsyncSession, material_id) -> Decimal:
    """Total on-hand across every location for one material.

    Returns ``Decimal('0')`` when no row exists (a freshly created
    material before its first receipt).
    """
    stmt = select(func.coalesce(func.sum(InventoryOnHand.on_hand), 0)).where(
        InventoryOnHand.entity_kind == "material",
        InventoryOnHand.entity_id == material_id,
    )
    raw = (await session.execute(stmt)).scalar_one()
    return _to_decimal(raw)


@projection(
    event_type=TYPE_MATERIAL_RECEIVED,
    name=HANDLER_NAME,
    read_model_tables=READ_MODEL_TABLES,
)
async def project_material_cost(event: Event, session: AsyncSession) -> None:
    """Apply one ``inventory.MaterialReceived`` event."""
    payload = event.payload or {}
    material_id = event.aggregate_id

    receipt_grams = _to_decimal(payload["grams"])
    receipt_unit_cost = _to_decimal(payload["unit_cost_at_receipt"])

    cost_row = (
        await session.execute(
            select(Material.current_cost_per_gram).where(Material.id == material_id)
        )
    ).first()
    if cost_row is None:
        # Parent material was deleted between event append and replay.
        return
    old_cost = _to_decimal(cost_row[0])
    # The on-hand projection has already applied this receipt's
    # quantity to ``inventory_on_hand``; back it out to recover the
    # prior balance.
    current_on_hand = await _sum_on_hand_for_material(session, material_id)
    old_on_hand = current_on_hand - receipt_grams
    if old_on_hand < 0:
        # Guard: if the on-hand projection's row was somehow missed, we
        # collapse to the "first receipt" branch below.
        old_on_hand = Decimal("0")

    if old_on_hand == 0:
        new_cost = receipt_unit_cost.quantize(_QUANTUM, rounding=ROUND_HALF_UP)
    else:
        numerator = old_on_hand * old_cost + receipt_grams * receipt_unit_cost
        denominator = old_on_hand + receipt_grams
        new_cost = (numerator / denominator).quantize(_QUANTUM, rounding=ROUND_HALF_UP)

    await session.execute(
        update(Material).where(Material.id == material_id).values(current_cost_per_gram=new_cost)
    )
    await session.flush()
