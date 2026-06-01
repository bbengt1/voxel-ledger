"""Pydantic schemas for the inventory on-hand + low-stock alerts API
surface (Phase 3.3, #52)."""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# Includes ``part`` (assembly-line epic #267): jobs credit part stock and
# builds consume it, so part on-hand must be queryable + serializable.
EntityKindLiteral = Literal["material", "supply", "product", "part"]


class OnHandRowResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    entity_kind: EntityKindLiteral
    entity_id: uuid.UUID
    location_id: uuid.UUID
    on_hand: Decimal


class OnHandSummaryResponse(BaseModel):
    """Aggregated across locations for a single entity."""

    entity_kind: EntityKindLiteral
    entity_id: uuid.UUID
    total_on_hand: Decimal
    per_location: dict[uuid.UUID, Decimal] = Field(default_factory=dict)


class OnHandListResponse(BaseModel):
    rows: list[OnHandRowResponse] = Field(default_factory=list)
    summaries: list[OnHandSummaryResponse] = Field(default_factory=list)


class LowStockAlertResponse(BaseModel):
    entity_kind: EntityKindLiteral
    entity_id: uuid.UUID
    entity_name: str
    threshold: Decimal
    total_on_hand: Decimal
    deficit: Decimal


class LowStockAlertListResponse(BaseModel):
    items: list[LowStockAlertResponse] = Field(default_factory=list)
