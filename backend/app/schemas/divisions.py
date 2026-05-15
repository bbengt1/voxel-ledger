"""Pydantic schemas for the divisions API surface (Phase 4.5, #68)."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class DivisionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    code: str
    is_archived: bool
    created_at: datetime
    updated_at: datetime


class DivisionCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    code: str = Field(min_length=1, max_length=32)


class DivisionUpdateRequest(BaseModel):
    """PATCH-style — only ``name`` is editable. The router rejects any
    ``code`` field (immutable post-create)."""

    name: str | None = Field(default=None, min_length=1, max_length=255)


class DivisionListResponse(BaseModel):
    items: list[DivisionResponse]
    next_cursor: str | None = None
