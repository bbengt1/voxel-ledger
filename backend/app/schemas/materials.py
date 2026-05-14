"""Pydantic schemas for the materials API surface (Phase 2.1, 3.3)."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class MaterialResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    brand: str | None = None
    material_type: str
    color: str | None = None
    density_g_per_cm3: Decimal | None = None
    current_cost_per_gram: Decimal
    # Phase 3.3 (#52): on-hand grams now live in ``inventory_on_hand``;
    # the API exposes the cross-location total plus a per-location map.
    total_on_hand: Decimal = Field(default=Decimal("0"))
    per_location_on_hand: dict[uuid.UUID, Decimal] = Field(default_factory=dict)
    low_stock_threshold_grams: Decimal | None = None
    is_archived: bool
    custom_fields: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class MaterialReceiptResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    material_id: uuid.UUID
    received_at: datetime
    grams: Decimal
    total_cost: Decimal
    unit_cost_at_receipt: Decimal
    vendor: str | None = None
    reference: str | None = None
    notes: str | None = None


class MaterialDetailResponse(MaterialResponse):
    """Material + the most recent 10 receipts (newest first)."""

    recent_receipts: list[MaterialReceiptResponse] = Field(default_factory=list)


class MaterialCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    brand: str | None = Field(default=None, max_length=255)
    material_type: str = Field(min_length=1, max_length=64)
    color: str | None = Field(default=None, max_length=64)
    density_g_per_cm3: Decimal | None = Field(default=None, ge=0)
    low_stock_threshold_grams: Decimal | None = Field(default=None, ge=0)
    custom_fields: dict[str, Any] | None = None


class MaterialUpdateRequest(BaseModel):
    """PATCH-style — only fields the user wants to change."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    brand: str | None = Field(default=None, max_length=255)
    material_type: str | None = Field(default=None, min_length=1, max_length=64)
    color: str | None = Field(default=None, max_length=64)
    density_g_per_cm3: Decimal | None = Field(default=None, ge=0)
    low_stock_threshold_grams: Decimal | None = Field(default=None, ge=0)
    custom_fields: dict[str, Any] | None = None


class MaterialListResponse(BaseModel):
    items: list[MaterialResponse]
    next_cursor: str | None = None


class MaterialReceiptCreateRequest(BaseModel):
    grams: Decimal = Field(gt=0)
    total_cost: Decimal = Field(ge=0)
    vendor: str | None = Field(default=None, max_length=255)
    reference: str | None = Field(default=None, max_length=255)
    notes: str | None = None


class MaterialReceiptListResponse(BaseModel):
    items: list[MaterialReceiptResponse]
    next_cursor: str | None = None
