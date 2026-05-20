"""Pydantic schemas for the trial-balance API (Phase 10.4, #179)."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from pydantic import BaseModel


class TrialBalanceRowResponse(BaseModel):
    account_id: uuid.UUID
    code: str
    name: str
    type: str
    opening_balance: Decimal
    period_debit: Decimal
    period_credit: Decimal
    closing_balance: Decimal


class TrialBalanceResponse(BaseModel):
    date_from: date
    date_to: date
    division_id: uuid.UUID | None = None
    include_zero: bool
    rows: list[TrialBalanceRowResponse]
    total_period_debit: Decimal
    total_period_credit: Decimal
