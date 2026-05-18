"""Pydantic schemas for the tax-profile API surface (Phase 9.5, #157)."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class TaxRateCreate(BaseModel):
    ordinal: int = Field(ge=0)
    name: str = Field(min_length=1, max_length=64)
    rate: Decimal
    liability_account_id: uuid.UUID
    compound_on_previous: bool = False


class TaxRateUpdate(BaseModel):
    ordinal: int | None = Field(default=None, ge=0)
    name: str | None = Field(default=None, min_length=1, max_length=64)
    rate: Decimal | None = None
    liability_account_id: uuid.UUID | None = None
    compound_on_previous: bool | None = None


class TaxRateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    profile_id: uuid.UUID
    ordinal: int
    name: str
    rate: Decimal
    liability_account_id: uuid.UUID
    compound_on_previous: bool
    created_at: datetime
    updated_at: datetime


class TaxProfileCreate(BaseModel):
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=255)
    jurisdiction: str = Field(min_length=1, max_length=64)
    is_reverse_charge: bool = False
    notes: str | None = None


class TaxProfileUpdate(BaseModel):
    code: str | None = Field(default=None, min_length=1, max_length=64)
    name: str | None = Field(default=None, min_length=1, max_length=255)
    jurisdiction: str | None = Field(default=None, min_length=1, max_length=64)
    is_reverse_charge: bool | None = None
    notes: str | None = None
    is_active: bool | None = None


class TaxProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    name: str
    jurisdiction: str
    is_reverse_charge: bool
    notes: str | None = None
    is_active: bool
    created_by_user_id: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime
    rates: list[TaxRateResponse] = []


class TaxProfileListResponse(BaseModel):
    items: list[TaxProfileResponse]
