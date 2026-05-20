"""Pydantic schemas for the balance-sheet API (Phase 10.2, #177)."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from pydantic import BaseModel


class BalanceSheetRowResponse(BaseModel):
    account_id: uuid.UUID
    code: str
    name: str
    depth: int
    section: str
    balance: Decimal


class BalanceSheetResponse(BaseModel):
    as_of: date
    division_id: uuid.UUID | None = None
    asset_rows: list[BalanceSheetRowResponse]
    liability_rows: list[BalanceSheetRowResponse]
    equity_rows: list[BalanceSheetRowResponse]
    total_assets: Decimal
    total_liabilities: Decimal
    total_equity: Decimal
    total_liabilities_and_equity: Decimal
    imbalance: Decimal
