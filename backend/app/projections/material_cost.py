"""Projection: weighted-average cost-per-gram + on-hand inventory.

Subscribes to ``inventory.MaterialReceived``. Recomputes the parent
material's ``current_cost_per_gram`` and ``on_hand_grams`` using a
running weighted average:

    new_cost = (old_on_hand * old_cost + receipt_grams * receipt_unit_cost)
               / (old_on_hand + receipt_grams)
    new_on_hand = old_on_hand + receipt_grams

Edge: if ``old_on_hand == 0`` the formula above is ``0/grams`` for the
weighted term, so ``new_cost = receipt_unit_cost`` directly.

Decimal arithmetic only — no floats anywhere on the math path. The
final values are quantized to 6 decimal places, matching the
``Numeric(18, 6)`` column precision.

Replay safety
-------------
The handler is idempotent in the sense that replaying the full event
stream from position 0 against a freshly-truncated material reproduces
the exact same ``(current_cost_per_gram, on_hand_grams)`` values that
live-projection produced. This is the "cost engine honesty" invariant
Phase 5 depends on.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.events.types.inventory import TYPE_MATERIAL_RECEIVED
from app.models.event import Event
from app.models.material import Material
from app.projections.registry import projection

HANDLER_NAME = "material_cost_projection"
READ_MODEL_TABLES: tuple[str, ...] = ("material",)

# Quantize to 6 decimal places at the end of every recompute. Matches
# the Numeric(18, 6) column precision.
_QUANTUM = Decimal("0.000001")


def _to_decimal(value: object) -> Decimal:
    """Coerce a payload value (already canonical-string from the event
    log) to Decimal. Raises if the value can't be parsed — callers should
    only ever pass values that came out of a registered payload model.
    """
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


@projection(
    event_type=TYPE_MATERIAL_RECEIVED,
    name=HANDLER_NAME,
    read_model_tables=READ_MODEL_TABLES,
)
async def project_material_cost(event: Event, session: AsyncSession) -> None:
    """Apply one ``inventory.MaterialReceived`` event to the material row.

    Loads the current ``(on_hand_grams, current_cost_per_gram)``,
    computes the new running weighted average, and writes it back. Runs
    inside the same transaction as ``EventStore.append`` so the event
    row, the receipt row, and the material's updated cache become
    durable atomically.
    """
    payload = event.payload or {}
    material_id = event.aggregate_id

    receipt_grams = _to_decimal(payload["grams"])
    receipt_unit_cost = _to_decimal(payload["unit_cost_at_receipt"])

    row = (
        await session.execute(
            select(Material.on_hand_grams, Material.current_cost_per_gram).where(
                Material.id == material_id
            )
        )
    ).first()
    if row is None:
        # The parent material was deleted between event append and
        # replay. Nothing to project against. The audit log still has
        # the event row.
        return

    old_on_hand, old_cost = row
    old_on_hand = _to_decimal(old_on_hand)
    old_cost = _to_decimal(old_cost)

    new_on_hand = (old_on_hand + receipt_grams).quantize(_QUANTUM, rounding=ROUND_HALF_UP)

    if old_on_hand == 0:
        new_cost = receipt_unit_cost.quantize(_QUANTUM, rounding=ROUND_HALF_UP)
    else:
        numerator = old_on_hand * old_cost + receipt_grams * receipt_unit_cost
        denominator = old_on_hand + receipt_grams
        new_cost = (numerator / denominator).quantize(_QUANTUM, rounding=ROUND_HALF_UP)

    # Direct UPDATE rather than fetching the ORM row. This keeps the
    # projection cheap and avoids any chance of touching columns we
    # don't own.
    from sqlalchemy import update

    await session.execute(
        update(Material)
        .where(Material.id == material_id)
        .values(
            current_cost_per_gram=new_cost,
            on_hand_grams=new_on_hand,
        )
    )
    await session.flush()
