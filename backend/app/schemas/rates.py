"""Pydantic schemas for the rates API surface (Phase 2.2)."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.rate import RateKind


class RateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    kind: RateKind
    value: Decimal
    applies_to_printer_id: uuid.UUID | None = None
    is_default_for_kind: bool
    is_archived: bool
    custom_fields: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class RateCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    kind: RateKind
    value: Decimal = Field(ge=0)
    applies_to_printer_id: uuid.UUID | None = None
    is_default_for_kind: bool = False
    custom_fields: dict[str, Any] | None = None


class RateUpdateRequest(BaseModel):
    """PATCH-style — only fields the user wants to change.

    ``is_default_for_kind`` is intentionally not editable here; use the
    dedicated ``set-default`` endpoint to flip it atomically.
    """

    name: str | None = Field(default=None, min_length=1, max_length=255)
    value: Decimal | None = Field(default=None, ge=0)
    applies_to_printer_id: uuid.UUID | None = None
    custom_fields: dict[str, Any] | None = None


class RateListResponse(BaseModel):
    items: list[RateResponse]
    next_cursor: str | None = None
