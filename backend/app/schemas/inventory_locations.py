"""Pydantic schemas for the inventory-locations API surface (Phase 3.1)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

InventoryLocationKindLiteral = Literal[
    "workshop",
    "finished_goods",
    "staging",
    "customer_pickup",
    "consignment",
    "virtual",
]


class InventoryLocationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    code: str
    kind: InventoryLocationKindLiteral
    description: str | None = None
    is_archived: bool
    created_at: datetime
    updated_at: datetime


class InventoryLocationCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    code: str = Field(min_length=1, max_length=32)
    kind: InventoryLocationKindLiteral
    description: str | None = Field(default=None, max_length=4096)


class InventoryLocationUpdateRequest(BaseModel):
    """PATCH-style — only fields the user wants to change."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    code: str | None = Field(default=None, min_length=1, max_length=32)
    kind: InventoryLocationKindLiteral | None = None
    description: str | None = Field(default=None, max_length=4096)


class InventoryLocationListResponse(BaseModel):
    items: list[InventoryLocationResponse]
    next_cursor: str | None = None
