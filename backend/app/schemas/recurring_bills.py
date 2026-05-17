"""Pydantic schemas for recurring bill templates (Phase 8.5, #132)."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

RecurringBillCadenceKindLiteral = Literal["daily", "weekly", "monthly", "quarterly", "yearly"]
RecurringBillTemplateStateLiteral = Literal["active", "paused", "cancelled"]
RecurringBillItemKindLiteral = Literal["expense_category", "manual"]


class RecurringBillTemplateItemCreate(BaseModel):
    kind: RecurringBillItemKindLiteral
    expense_category_id: uuid.UUID | None = None
    description: str = Field(min_length=1)
    vendor_sku: str | None = Field(default=None, max_length=64)
    quantity: Decimal = Field(default=Decimal("1"))
    unit_price: Decimal


class RecurringBillTemplateItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    line_number: int
    kind: RecurringBillItemKindLiteral
    expense_category_id: uuid.UUID | None = None
    description: str
    vendor_sku: str | None = None
    quantity: Decimal
    unit_price: Decimal


class RecurringBillTemplateCreate(BaseModel):
    vendor_id: uuid.UUID
    name: str = Field(min_length=1, max_length=200)
    cadence_kind: RecurringBillCadenceKindLiteral
    cadence_interval: int = Field(default=1, ge=1)
    start_at: datetime
    end_at: datetime | None = None
    auto_issue: bool = False
    notes: str | None = None
    discount_amount: Decimal = Field(default=Decimal("0"))
    tax_amount: Decimal = Field(default=Decimal("0"))
    currency: str = Field(default="USD", min_length=3, max_length=3)
    items: list[RecurringBillTemplateItemCreate] = Field(default_factory=list)


class RecurringBillTemplateUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    cadence_kind: RecurringBillCadenceKindLiteral | None = None
    cadence_interval: int | None = Field(default=None, ge=1)
    start_at: datetime | None = None
    end_at: datetime | None = None
    auto_issue: bool | None = None
    notes: str | None = None
    discount_amount: Decimal | None = None
    tax_amount: Decimal | None = None
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    items: list[RecurringBillTemplateItemCreate] | None = None


class RecurringBillTemplateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    vendor_id: uuid.UUID
    name: str
    cadence_kind: RecurringBillCadenceKindLiteral
    cadence_interval: int
    start_at: datetime
    end_at: datetime | None = None
    next_issue_at: datetime
    last_issued_at: datetime | None = None
    auto_issue: bool
    state: RecurringBillTemplateStateLiteral
    notes: str | None = None
    discount_amount: Decimal
    tax_amount: Decimal
    currency: str
    created_by_user_id: uuid.UUID
    created_at: datetime
    updated_at: datetime
    items: list[RecurringBillTemplateItemResponse] = Field(default_factory=list)


class RecurringBillTemplateListResponse(BaseModel):
    items: list[RecurringBillTemplateResponse]
    next_cursor: str | None = None


class RecurringBillTemplateStateTransitionRequest(BaseModel):
    note: str | None = None


class RecurringBillMaterializeResponse(BaseModel):
    template_id: uuid.UUID
    bill_id: uuid.UUID
    bill_number: str
    materialized_at: datetime
    auto_issued: bool
    next_issue_at: datetime | None = None
