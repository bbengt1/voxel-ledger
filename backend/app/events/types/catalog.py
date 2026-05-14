"""Catalog-bounded-context event types (Phase 2.1).

The catalog domain owns materials (this issue), products, and option
schemas in later phases. Each material mutation is a domain event:
creation, profile update (with diff), archive, unarchive.

Aggregate type is ``material``; aggregate_id is the material row id.
``actor_user_id`` on the event row is the admin / production user
performing the action.
"""

from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.events.registry import register_event

AGGREGATE_TYPE: str = "material"


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
