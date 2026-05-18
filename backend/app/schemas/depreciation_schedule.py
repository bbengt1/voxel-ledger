"""Pydantic schemas for the depreciation-schedule API surface (Phase 9.2, #154)."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict

DepreciationEntryStateLiteral = Literal["planned", "posted", "adjusted"]


class DepreciationScheduleEntryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    asset_id: uuid.UUID
    period_index: int
    period_end: date
    opening_book_value: Decimal
    depreciation_amount: Decimal
    closing_book_value: Decimal
    state: DepreciationEntryStateLiteral
    journal_entry_id: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime


class DepreciationScheduleResponse(BaseModel):
    asset_id: uuid.UUID
    entries: list[DepreciationScheduleEntryResponse]
    total_depreciation: Decimal
