"""Pydantic schemas for the budgets API surface (Phase 4.5, #68)."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.accounts import AccountTypeLiteral


class BudgetUpsertRequest(BaseModel):
    account_id: uuid.UUID
    division_id: uuid.UUID | None = None
    period_id: uuid.UUID
    amount: Decimal = Field(ge=Decimal("0"))

    @field_validator("amount")
    @classmethod
    def _non_negative(cls, value: Decimal) -> Decimal:
        if value < 0:
            raise ValueError("amount must be >= 0")
        return value


class BudgetDeleteRequest(BaseModel):
    account_id: uuid.UUID
    division_id: uuid.UUID | None = None
    period_id: uuid.UUID


class BudgetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    account_id: uuid.UUID
    account_code: str
    account_name: str
    account_type: AccountTypeLiteral
    division_id: uuid.UUID | None = None
    division_name: str | None = None
    division_code: str | None = None
    period_id: uuid.UUID
    amount: Decimal
    created_at: datetime
    updated_at: datetime


class BudgetListResponse(BaseModel):
    items: list[BudgetResponse]


class BudgetVarianceRow(BaseModel):
    account_id: uuid.UUID
    account_code: str
    account_name: str
    account_type: AccountTypeLiteral
    division_id: uuid.UUID | None = None
    division_name: str | None = None
    budget_amount: Decimal
    actual_amount: Decimal
    variance: Decimal
    variance_pct: Decimal


class BudgetVarianceSummaryResponse(BaseModel):
    period_id: uuid.UUID
    items: list[BudgetVarianceRow]
