"""Pydantic schemas for the accounting-periods API surface (Phase 4.3, #66)."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

AccountingPeriodStateLiteral = Literal["open", "closed", "locked"]


class AccountingPeriodCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    start_date: date
    end_date: date


class AccountingPeriodUpdate(BaseModel):
    """Only the display name is mutable post-create. Dates are immutable."""

    name: str = Field(min_length=1, max_length=64)


class AccountingPeriodResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    start_date: date
    end_date: date
    state: AccountingPeriodStateLiteral
    closed_at: datetime | None = None
    closed_by_user_id: uuid.UUID | None = None
    locked_at: datetime | None = None
    locked_by_user_id: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime


class AccountingPeriodListResponse(BaseModel):
    items: list[AccountingPeriodResponse]
    next_cursor: str | None = None
