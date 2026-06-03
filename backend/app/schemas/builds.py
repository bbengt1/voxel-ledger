"""Pydantic schemas for the builds API surface (assembly-line epic #267,
Phase 5).

A Build assembles N of a product from its parts + supplies. The
``preview`` shapes drive the UI's pre-flight (required components, on-hand
availability, shortfalls, and live cost) so a user can review a build
before it consumes stock.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

BuildStateLiteral = Literal["draft", "completed", "cancelled"]


class BuildCreate(BaseModel):
    product_id: uuid.UUID
    quantity: int = Field(gt=0)
    # Optional override; defaults to product.assembly_minutes x quantity.
    assembly_minutes: int | None = Field(default=None, ge=0)
    notes: str | None = Field(default=None, max_length=4096)


class BuildUpdate(BaseModel):
    quantity: int | None = Field(default=None, gt=0)
    assembly_minutes: int | None = Field(default=None, ge=0)
    notes: str | None = Field(default=None, max_length=4096)


class BuildResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    build_number: str
    product_id: uuid.UUID
    state: BuildStateLiteral
    quantity: int
    assembly_minutes: int
    location_id: uuid.UUID | None = None
    unit_cost_cached: Decimal | None = None
    total_cost_cached: Decimal | None = None
    notes: str | None = None
    actor_user_id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class BuildListResponse(BaseModel):
    items: list[BuildResponse]
    next_cursor: str | None = None


class BuildPlanLine(BaseModel):
    """One required part/supply for a build, with availability."""

    component_kind: Literal["part", "supply"]
    component_id: uuid.UUID
    name: str
    quantity_per_product: Decimal
    required_quantity: Decimal
    on_hand: Decimal
    sufficient: bool
    unit_cost: Decimal | None = None
    line_cost: Decimal | None = None


class BuildPlanResponse(BaseModel):
    """Pre-flight for a proposed build: required components + cost.

    ``can_build`` is true only when every line has enough on-hand at the
    resolved consumption location.
    """

    product_id: uuid.UUID
    quantity: int
    assembly_minutes: int
    location_id: uuid.UUID | None = None
    lines: list[BuildPlanLine] = Field(default_factory=list)
    component_cost: Decimal | None = None
    assembly_labor_cost: Decimal | None = None
    unit_cost: Decimal | None = None
    total_cost: Decimal | None = None
    can_build: bool = False


class BuildPreviewRequest(BaseModel):
    product_id: uuid.UUID
    quantity: int = Field(gt=0)
    assembly_minutes: int | None = Field(default=None, ge=0)


class BuildNowRequest(BaseModel):
    """One-shot build from the product page: create + complete in one call,
    consuming parts/supplies and crediting the product immediately."""

    product_id: uuid.UUID
    quantity: int = Field(gt=0)


class BuildableResponse(BaseModel):
    """How many whole units of a product can be assembled right now from
    on-hand parts + supplies at the resolved consumption location."""

    product_id: uuid.UUID
    location_id: uuid.UUID | None = None
    max_buildable: int
