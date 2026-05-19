"""Pydantic schemas for the withholding-profile API (Phase 9.7, #159)."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class WithholdingProfileCreate(BaseModel):
    code: str
    name: str
    jurisdiction: str
    rate: Decimal
    liability_account_id: uuid.UUID
    threshold_per_year: Decimal | None = None
    form_kind: str | None = None
    notes: str | None = None


class WithholdingProfileUpdate(BaseModel):
    name: str | None = None
    jurisdiction: str | None = None
    rate: Decimal | None = None
    liability_account_id: uuid.UUID | None = None
    threshold_per_year: Decimal | None = None
    form_kind: str | None = None
    notes: str | None = None


class WithholdingProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    name: str
    jurisdiction: str
    rate: Decimal
    liability_account_id: uuid.UUID
    threshold_per_year: Decimal | None = None
    form_kind: str | None = None
    notes: str | None = None
    is_active: bool
    created_by_user_id: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime


class WithholdingProfileListResponse(BaseModel):
    items: list[WithholdingProfileResponse]


class VendorYtdPaymentsResponse(BaseModel):
    vendor_id: uuid.UUID
    year: int
    total_paid: Decimal


class WithholdingYtdRowResponse(BaseModel):
    vendor_id: uuid.UUID
    vendor_number: str
    display_name: str
    profile_id: uuid.UUID | None = None
    profile_code: str | None = None
    form_kind: str | None = None
    total_paid: Decimal
    total_withheld: Decimal


class WithholdingYtdReportResponse(BaseModel):
    year: int
    rows: list[WithholdingYtdRowResponse]
    grand_total_paid: Decimal
    grand_total_withheld: Decimal
