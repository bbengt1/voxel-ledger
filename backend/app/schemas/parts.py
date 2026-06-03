"""Pydantic schemas for the parts API (assembly-line epic #267, Phase 1)."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class PartCreateRequest(BaseModel):
    # SKU auto-allocated as PART-YYYY-NNNN when omitted.
    sku: str | None = Field(default=None, min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    # Print recipe.
    print_minutes: int = Field(default=0, ge=0)
    setup_minutes: int = Field(default=0, ge=0)
    parts_per_run: int = Field(default=1, gt=0)
    print_grams_by_material: dict[uuid.UUID, Decimal] = Field(default_factory=dict)
    assigned_printer_ids: list[uuid.UUID] = Field(default_factory=list)
    custom_fields: dict[str, Any] | None = None


class PartUpdateRequest(BaseModel):
    """PATCH-style: only fields the caller wants to change."""

    sku: str | None = Field(default=None, min_length=1, max_length=64)
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    print_minutes: int | None = Field(default=None, ge=0)
    setup_minutes: int | None = Field(default=None, ge=0)
    parts_per_run: int | None = Field(default=None, gt=0)
    print_grams_by_material: dict[uuid.UUID, Decimal] | None = None
    assigned_printer_ids: list[uuid.UUID] | None = None
    custom_fields: dict[str, Any] | None = None


class PartResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    sku: str
    name: str
    description: str | None = None
    print_minutes: int
    setup_minutes: int
    parts_per_run: int
    print_grams_by_material: dict[str, str] = Field(default_factory=dict)
    assigned_printer_ids: list[str] = Field(default_factory=list)
    # Populated by the Phase 2 cost rollup; null until then.
    unit_cost_cached: Decimal | None = None
    # Total on-hand summed across all locations. Defaults to 0 when the
    # caller builds a response straight from the ORM row; the parts list +
    # detail endpoints fill it in.
    total_on_hand: Decimal = Decimal("0")
    # Per-location on-hand breakdown ({location_id: qty}). Populated by the
    # detail endpoint; empty on list/ORM-built responses.
    per_location_on_hand: dict[uuid.UUID, Decimal] = Field(default_factory=dict)
    is_archived: bool
    custom_fields: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class PartListResponse(BaseModel):
    items: list[PartResponse]
    next_cursor: str | None = None
