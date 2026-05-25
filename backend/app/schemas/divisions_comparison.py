"""Pydantic schemas for the divisions-comparison report (Parity #229)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import BaseModel


class ComparisonColumnResponse(BaseModel):
    division_id: str
    code: str
    label: str


class ComparisonRowResponse(BaseModel):
    account_id: str
    code: str
    name: str
    section: str
    amounts: dict[str, Decimal]


class DivisionsComparisonResponse(BaseModel):
    date_from: date
    date_to: date
    columns: list[ComparisonColumnResponse]
    revenue_rows: list[ComparisonRowResponse]
    cogs_rows: list[ComparisonRowResponse]
    operating_expense_rows: list[ComparisonRowResponse]
    total_revenue: dict[str, Decimal]
    total_cogs: dict[str, Decimal]
    gross_profit: dict[str, Decimal]
    total_operating_expenses: dict[str, Decimal]
    operating_income: dict[str, Decimal]
    net_income: dict[str, Decimal]


__all__ = [
    "ComparisonColumnResponse",
    "ComparisonRowResponse",
    "DivisionsComparisonResponse",
]
