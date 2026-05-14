"""Inventory-bounded-context event types (Phase 2.1).

The inventory domain owns physical-stock movements: receipts (this
issue), consumption by jobs, write-offs (later phases).

``inventory.MaterialReceived`` is emitted when a material receipt is
recorded. The ``material_cost`` projection consumes it to recompute the
weighted-average cost-per-gram and on-hand grams in the same transaction
as the event.

Decimal payload fields are stored as canonical strings so the registry
round-trips them losslessly through JSON. Callers should pass
``Decimal`` instances; Pydantic v2 will serialize them via ``mode='json'``
in ``EventStore.append``'s ``validate_payload`` step.

Aggregate type is ``material`` (the receipt mutates a material's
inventory state — the receipt row itself is incidental).
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.events.registry import register_event

AGGREGATE_TYPE: str = "material"


class _InventoryPayloadBase(BaseModel):
    model_config = ConfigDict(extra="forbid")


class MaterialReceivedPayload(_InventoryPayloadBase):
    """One material receipt event.

    Decimals are serialized to canonical strings by Pydantic's
    ``mode='json'`` dump, which is what the event registry stores.
    """

    material_id: uuid.UUID
    grams: Decimal
    total_cost: Decimal
    unit_cost_at_receipt: Decimal
    vendor: str | None = None
    reference: str | None = None


TYPE_MATERIAL_RECEIVED = "inventory.MaterialReceived"


register_event(TYPE_MATERIAL_RECEIVED, MaterialReceivedPayload)
