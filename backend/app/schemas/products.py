"""Pydantic schemas for the products API surface (Phase 2.3)."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class ProductResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    sku: str
    upc: str | None = None
    name: str
    description: str | None = None
    unit_price: Decimal
    # Computed by the Phase 2.4 BOM rollup; null until BOM exists.
    unit_cost_cached: Decimal | None = None
    weight_grams: Decimal | None = None
    category: str | None = None
    is_archived: bool
    created_at: datetime
    updated_at: datetime


class ProductCreateRequest(BaseModel):
    # All optional fields with their constraints; SKU is auto-allocated
    # if omitted.
    sku: str | None = Field(default=None, min_length=1, max_length=64)
    upc: str | None = Field(default=None, min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    unit_price: Decimal = Field(ge=0)
    weight_grams: Decimal | None = Field(default=None, ge=0)
    category: str | None = Field(default=None, max_length=64)


class ProductUpdateRequest(BaseModel):
    """PATCH-style: only fields the caller wants to change."""

    sku: str | None = Field(default=None, min_length=1, max_length=64)
    upc: str | None = Field(default=None, max_length=64)
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    unit_price: Decimal | None = Field(default=None, ge=0)
    weight_grams: Decimal | None = Field(default=None, ge=0)
    category: str | None = Field(default=None, max_length=64)


class ProductListResponse(BaseModel):
    items: list[ProductResponse]
    next_cursor: str | None = None
