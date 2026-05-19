"""Pydantic schemas for the tax-remittance API (Phase 9.6, #158)."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict

TaxRemittanceMethodLiteral = Literal["ach", "check", "wire", "other"]
TaxRemittanceStateLiteral = Literal["recorded", "cancelled"]


class TaxRemittanceCreate(BaseModel):
    profile_id: uuid.UUID
    period_start: date
    period_end: date
    amount_paid: Decimal
    paid_on: date
    method: TaxRemittanceMethodLiteral
    bank_account_id: uuid.UUID
    reference_number: str | None = None
    notes: str | None = None
    allow_partial: bool = False


class TaxRemittanceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    remittance_number: str
    profile_id: uuid.UUID
    period_start: date
    period_end: date
    amount_paid: Decimal
    paid_on: date
    method: TaxRemittanceMethodLiteral
    reference_number: str | None = None
    bank_account_id: uuid.UUID
    state: TaxRemittanceStateLiteral
    posting_journal_entry_id: uuid.UUID | None = None
    notes: str | None = None
    created_by_user_id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class TaxRemittanceListResponse(BaseModel):
    items: list[TaxRemittanceResponse]
    next_cursor: str | None = None


# --- Tax-liability report ---------------------------------------------------


class TaxLiabilityRowResponse(BaseModel):
    profile_id: uuid.UUID
    profile_code: str
    profile_name: str
    jurisdiction: str
    rate_id: uuid.UUID
    rate_name: str
    rate: Decimal
    compound_on_previous: bool
    tax_collected: Decimal
    tax_remitted: Decimal
    net_liability: Decimal
    gross_taxable_sales: Decimal


class TaxLiabilityReportResponse(BaseModel):
    date_from: date
    date_to: date
    rows: list[TaxLiabilityRowResponse]
    grand_total_collected: Decimal
    grand_total_remitted: Decimal
    grand_total_net: Decimal
