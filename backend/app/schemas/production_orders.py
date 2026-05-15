"""Pydantic schemas for production orders + job discovery (Phase 5.5, #81)."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ProductionOrderStateLiteral = Literal["planning", "active", "completed", "archived"]


# --- Production order ------------------------------------------------------


class ProductionOrderCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    priority: int = Field(default=0)
    due_at: datetime | None = None
    notes: str | None = Field(default=None, max_length=4096)


class ProductionOrderUpdate(BaseModel):
    """Editable fields after create: ``name``, ``priority``, ``due_at``, ``notes``."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    priority: int | None = None
    due_at: datetime | None = None
    notes: str | None = Field(default=None, max_length=4096)


class ProductionOrderJobMember(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    job_id: uuid.UUID
    display_order: int


class ProductionOrderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    order_number: str
    name: str
    state: ProductionOrderStateLiteral
    priority: int
    due_at: datetime | None = None
    notes: str | None = None
    created_by_user_id: uuid.UUID
    created_at: datetime
    updated_at: datetime
    jobs: list[ProductionOrderJobMember] = Field(default_factory=list)


class ProductionOrderListResponse(BaseModel):
    items: list[ProductionOrderResponse]
    next_cursor: str | None = None


class JobMembershipRequest(BaseModel):
    job_id: uuid.UUID
    display_order: int | None = None


class JobReorderRequest(BaseModel):
    job_id: uuid.UUID
    new_position: int = Field(ge=0)


# --- Job discovery ---------------------------------------------------------


class DiscoveredPlateResponse(BaseModel):
    """Parser output. No DB writes — the UI uses this to pre-fill a plate form."""

    print_minutes: int
    filament_grams_by_material: dict[str, Decimal] = Field(default_factory=dict)
    parts_per_set: int = 1
    source_format: str = Field(description="prusaslicer | bambu")
    source_filename: str | None = None
