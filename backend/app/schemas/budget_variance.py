"""Pydantic schemas for the budget-variance report (Parity #227)."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from pydantic import BaseModel


class BudgetVarianceRowResponse(BaseModel):
    account_id: uuid.UUID
    code: str
    name: str
    section: str
    budget: Decimal
    actual: Decimal
    variance: Decimal
    variance_pct: Decimal | None = None


class BudgetVarianceResponse(BaseModel):
    period_id: uuid.UUID
    period_name: str
    date_from: date
    date_to: date
    division_id: uuid.UUID | None = None
    revenue_rows: list[BudgetVarianceRowResponse]
    cogs_rows: list[BudgetVarianceRowResponse]
    operating_expense_rows: list[BudgetVarianceRowResponse]
    total_revenue_budget: Decimal
    total_revenue_actual: Decimal
    total_cogs_budget: Decimal
    total_cogs_actual: Decimal
    total_operating_expense_budget: Decimal
    total_operating_expense_actual: Decimal


__all__ = ["BudgetVarianceResponse", "BudgetVarianceRowResponse"]
