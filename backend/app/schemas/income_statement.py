"""Pydantic schemas for the income-statement API (Phase 10.1, #176)."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from pydantic import BaseModel


class IncomeStatementRowResponse(BaseModel):
    account_id: uuid.UUID
    code: str
    name: str
    depth: int
    section: str
    amount: Decimal


class IncomeStatementResponse(BaseModel):
    date_from: date
    date_to: date
    division_id: uuid.UUID | None = None
    revenue_rows: list[IncomeStatementRowResponse]
    cogs_rows: list[IncomeStatementRowResponse]
    operating_expense_rows: list[IncomeStatementRowResponse]
    total_revenue: Decimal
    total_cogs: Decimal
    gross_profit: Decimal
    total_operating_expenses: Decimal
    operating_income: Decimal
    net_income: Decimal
