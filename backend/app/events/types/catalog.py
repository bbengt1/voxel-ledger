"""Catalog-bounded-context event types.

The catalog domain owns materials (Phase 2.1), products (Phase 2.3), and
option schemas in later phases. Each catalog mutation is a domain event:
creation, profile update (with diff), archive, unarchive, etc.

For materials the aggregate type is ``material`` and aggregate_id is the
material row id. For products it's ``product`` / product row id. The
``actor_user_id`` on the event row is the admin / production / sales user
performing the action.
"""

from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.events.registry import register_event

# Materials aggregate type. Products use PRODUCT_AGGREGATE_TYPE below.
AGGREGATE_TYPE: str = "material"
PRODUCT_AGGREGATE_TYPE: str = "product"


class _MaterialPayloadBase(BaseModel):
    model_config = ConfigDict(extra="forbid")


class MaterialCreatedPayload(_MaterialPayloadBase):
    material_id: uuid.UUID
    name: str
    brand: str | None = None
    material_type: str
    color: str | None = None


class MaterialUpdatedPayload(_MaterialPayloadBase):
    material_id: uuid.UUID
    # Only the fields that actually changed. Values are JSON-serializable
    # scalars; Decimals are serialized as canonical strings upstream.
    before: dict[str, Any]
    after: dict[str, Any]


class MaterialArchivedPayload(_MaterialPayloadBase):
    material_id: uuid.UUID


class MaterialUnarchivedPayload(_MaterialPayloadBase):
    material_id: uuid.UUID


TYPE_MATERIAL_CREATED = "catalog.MaterialCreated"
TYPE_MATERIAL_UPDATED = "catalog.MaterialUpdated"
TYPE_MATERIAL_ARCHIVED = "catalog.MaterialArchived"
TYPE_MATERIAL_UNARCHIVED = "catalog.MaterialUnarchived"


register_event(TYPE_MATERIAL_CREATED, MaterialCreatedPayload)
register_event(TYPE_MATERIAL_UPDATED, MaterialUpdatedPayload)
register_event(TYPE_MATERIAL_ARCHIVED, MaterialArchivedPayload)
register_event(TYPE_MATERIAL_UNARCHIVED, MaterialUnarchivedPayload)


# --- Products (Phase 2.3) -------------------------------------------------
#
# Product aggregate. Prices and Decimals serialize as canonical strings on
# the wire — see the materials-side helper for the same pattern.


class _ProductPayloadBase(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProductCreatedPayload(_ProductPayloadBase):
    product_id: uuid.UUID
    sku: str
    name: str
    unit_price: str
    category: str | None = None


class ProductUpdatedPayload(_ProductPayloadBase):
    product_id: uuid.UUID
    before: dict[str, Any]
    after: dict[str, Any]


class ProductPriceChangedPayload(_ProductPayloadBase):
    product_id: uuid.UUID
    old_price: str
    new_price: str


class ProductArchivedPayload(_ProductPayloadBase):
    product_id: uuid.UUID


class ProductUnarchivedPayload(_ProductPayloadBase):
    product_id: uuid.UUID


TYPE_PRODUCT_CREATED = "catalog.ProductCreated"
TYPE_PRODUCT_UPDATED = "catalog.ProductUpdated"
TYPE_PRODUCT_PRICE_CHANGED = "catalog.ProductPriceChanged"
TYPE_PRODUCT_ARCHIVED = "catalog.ProductArchived"
TYPE_PRODUCT_UNARCHIVED = "catalog.ProductUnarchived"


register_event(TYPE_PRODUCT_CREATED, ProductCreatedPayload)
register_event(TYPE_PRODUCT_UPDATED, ProductUpdatedPayload)
register_event(TYPE_PRODUCT_PRICE_CHANGED, ProductPriceChangedPayload)
register_event(TYPE_PRODUCT_ARCHIVED, ProductArchivedPayload)
register_event(TYPE_PRODUCT_UNARCHIVED, ProductUnarchivedPayload)
