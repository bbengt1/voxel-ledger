"""Inventory-bounded-context event types (Phase 2.1, 3.1).

The inventory domain owns physical-stock movements and the locations
stock lives in. ``inventory.MaterialReceived`` is emitted when a
material receipt is recorded. The ``material_cost`` projection consumes
it to recompute the weighted-average cost-per-gram and on-hand grams in
the same transaction as the event.

Phase 3.1 (#50) adds ``inventory.Location*`` lifecycle events for the
``inventory_location`` aggregate. These are catalog-style CRUD events;
no projection consumes them today beyond the wildcard audit log.

Decimal payload fields are stored as canonical strings so the registry
round-trips them losslessly through JSON.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.events.registry import register_event

# Material-receipt aggregate stays ``material`` for backwards-compat with #37.
AGGREGATE_TYPE: str = "material"
# Phase 3.1: inventory-location aggregate.
AGGREGATE_TYPE_INVENTORY_LOCATION: str = "inventory_location"


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


# --- Inventory locations (Phase 3.1) ---


class LocationCreatedPayload(_InventoryPayloadBase):
    location_id: uuid.UUID
    name: str
    code: str
    kind: str


class LocationUpdatedPayload(_InventoryPayloadBase):
    location_id: uuid.UUID
    before: dict[str, Any]
    after: dict[str, Any]


class LocationArchivedPayload(_InventoryPayloadBase):
    location_id: uuid.UUID


class LocationUnarchivedPayload(_InventoryPayloadBase):
    location_id: uuid.UUID


TYPE_LOCATION_CREATED = "inventory.LocationCreated"
TYPE_LOCATION_UPDATED = "inventory.LocationUpdated"
TYPE_LOCATION_ARCHIVED = "inventory.LocationArchived"
TYPE_LOCATION_UNARCHIVED = "inventory.LocationUnarchived"


register_event(TYPE_LOCATION_CREATED, LocationCreatedPayload)
register_event(TYPE_LOCATION_UPDATED, LocationUpdatedPayload)
register_event(TYPE_LOCATION_ARCHIVED, LocationArchivedPayload)
register_event(TYPE_LOCATION_UNARCHIVED, LocationUnarchivedPayload)


# --- Inventory transactions (Phase 3.2) ---

# Aggregate for inventory-transaction events. Each transaction is its
# own aggregate (one event per row); the row id is the aggregate_id.
AGGREGATE_TYPE_INVENTORY_TRANSACTION: str = "inventory_transaction"


class TransactionRecordedPayload(_InventoryPayloadBase):
    """One inventory-transaction row, captured at write time.

    Decimals are serialized to canonical strings; UUIDs to strings via
    Pydantic's ``mode='json'`` dump used by the event registry.
    """

    transaction_id: uuid.UUID
    kind: str
    entity_kind: str
    entity_id: uuid.UUID
    location_id: uuid.UUID
    # Signed magnitude — the service has already applied the sign.
    signed_quantity: Decimal
    unit_cost: Decimal | None = None
    total_cost: Decimal | None = None
    transfer_pair_id: uuid.UUID | None = None
    linked_job_id: uuid.UUID | None = None
    linked_sale_id: uuid.UUID | None = None
    reason: str | None = None


TYPE_TRANSACTION_RECORDED = "inventory.TransactionRecorded"


register_event(TYPE_TRANSACTION_RECORDED, TransactionRecordedPayload)
