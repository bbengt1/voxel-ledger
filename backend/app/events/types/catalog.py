"""Catalog-bounded-context event types.

The catalog domain owns materials (Phase 2.1), supplies + rates (Phase
2.2), products + options (Phase 2.3/2.4). Each mutation in any of those
sub-domains is a domain event with its own typed payload.

Aggregate type varies by sub-domain (``material``, ``supply``,
``rate``, ...). Service code passes the correct one when emitting.
``actor_user_id`` on the event row is the admin / production user
performing the action.
"""

from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.events.registry import register_event

# Default aggregate type for the materials sub-domain. Kept as the
# module-level constant for backwards compatibility with #37 callsites.
AGGREGATE_TYPE: str = "material"
AGGREGATE_TYPE_SUPPLY: str = "supply"
AGGREGATE_TYPE_RATE: str = "rate"


class _CatalogPayloadBase(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --- Materials ---


class MaterialCreatedPayload(_CatalogPayloadBase):
    material_id: uuid.UUID
    name: str
    brand: str | None = None
    material_type: str
    color: str | None = None


class MaterialUpdatedPayload(_CatalogPayloadBase):
    material_id: uuid.UUID
    # Only the fields that actually changed. Values are JSON-serializable
    # scalars; Decimals are serialized as canonical strings upstream.
    before: dict[str, Any]
    after: dict[str, Any]


class MaterialArchivedPayload(_CatalogPayloadBase):
    material_id: uuid.UUID


class MaterialUnarchivedPayload(_CatalogPayloadBase):
    material_id: uuid.UUID


TYPE_MATERIAL_CREATED = "catalog.MaterialCreated"
TYPE_MATERIAL_UPDATED = "catalog.MaterialUpdated"
TYPE_MATERIAL_ARCHIVED = "catalog.MaterialArchived"
TYPE_MATERIAL_UNARCHIVED = "catalog.MaterialUnarchived"


register_event(TYPE_MATERIAL_CREATED, MaterialCreatedPayload)
register_event(TYPE_MATERIAL_UPDATED, MaterialUpdatedPayload)
register_event(TYPE_MATERIAL_ARCHIVED, MaterialArchivedPayload)
register_event(TYPE_MATERIAL_UNARCHIVED, MaterialUnarchivedPayload)


# --- Supplies ---


class SupplyCreatedPayload(_CatalogPayloadBase):
    supply_id: uuid.UUID
    name: str
    unit: str
    unit_cost: str  # Decimal serialized as canonical string
    vendor: str | None = None


class SupplyUpdatedPayload(_CatalogPayloadBase):
    supply_id: uuid.UUID
    before: dict[str, Any]
    after: dict[str, Any]


class SupplyArchivedPayload(_CatalogPayloadBase):
    supply_id: uuid.UUID


class SupplyUnarchivedPayload(_CatalogPayloadBase):
    supply_id: uuid.UUID


TYPE_SUPPLY_CREATED = "catalog.SupplyCreated"
TYPE_SUPPLY_UPDATED = "catalog.SupplyUpdated"
TYPE_SUPPLY_ARCHIVED = "catalog.SupplyArchived"
TYPE_SUPPLY_UNARCHIVED = "catalog.SupplyUnarchived"


register_event(TYPE_SUPPLY_CREATED, SupplyCreatedPayload)
register_event(TYPE_SUPPLY_UPDATED, SupplyUpdatedPayload)
register_event(TYPE_SUPPLY_ARCHIVED, SupplyArchivedPayload)
register_event(TYPE_SUPPLY_UNARCHIVED, SupplyUnarchivedPayload)


# --- Rates ---


class RateCreatedPayload(_CatalogPayloadBase):
    rate_id: uuid.UUID
    name: str
    kind: str
    value: str  # Decimal serialized as canonical string
    is_default_for_kind: bool


class RateUpdatedPayload(_CatalogPayloadBase):
    rate_id: uuid.UUID
    before: dict[str, Any]
    after: dict[str, Any]


class RateDefaultedPayload(_CatalogPayloadBase):
    rate_id: uuid.UUID
    kind: str
    previous_default_rate_id: uuid.UUID | None = None


class RateArchivedPayload(_CatalogPayloadBase):
    rate_id: uuid.UUID


class RateUnarchivedPayload(_CatalogPayloadBase):
    rate_id: uuid.UUID


TYPE_RATE_CREATED = "catalog.RateCreated"
TYPE_RATE_UPDATED = "catalog.RateUpdated"
TYPE_RATE_DEFAULTED = "catalog.RateDefaulted"
TYPE_RATE_ARCHIVED = "catalog.RateArchived"
TYPE_RATE_UNARCHIVED = "catalog.RateUnarchived"


register_event(TYPE_RATE_CREATED, RateCreatedPayload)
register_event(TYPE_RATE_UPDATED, RateUpdatedPayload)
register_event(TYPE_RATE_DEFAULTED, RateDefaultedPayload)
register_event(TYPE_RATE_ARCHIVED, RateArchivedPayload)
register_event(TYPE_RATE_UNARCHIVED, RateUnarchivedPayload)
