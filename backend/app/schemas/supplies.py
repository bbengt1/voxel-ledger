"""Pydantic schemas for the supplies API surface (Phase 2.2)."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class SupplyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    unit: str
    unit_cost: Decimal
    vendor: str | None = None
    on_hand: Decimal
    is_archived: bool
    custom_fields: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class SupplyCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    unit: str = Field(min_length=1, max_length=32)
    unit_cost: Decimal = Field(ge=0)
    vendor: str | None = Field(default=None, max_length=255)
    on_hand: Decimal = Field(default=Decimal("0"), ge=0)
    custom_fields: dict[str, Any] | None = None


class SupplyUpdateRequest(BaseModel):
    """PATCH-style — only fields the user wants to change."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    unit: str | None = Field(default=None, min_length=1, max_length=32)
    unit_cost: Decimal | None = Field(default=None, ge=0)
    vendor: str | None = Field(default=None, max_length=255)
    custom_fields: dict[str, Any] | None = None


class SupplyListResponse(BaseModel):
    items: list[SupplyResponse]
    next_cursor: str | None = None
