"""Pydantic schemas for recurring invoice templates (Phase 7.5, #113)."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

RecurringCadenceKindLiteral = Literal["daily", "weekly", "monthly", "quarterly", "yearly"]
RecurringTemplateStateLiteral = Literal["active", "paused", "cancelled"]
RecurringInvoiceItemKindLiteral = Literal["product", "job", "manual"]


class RecurringTemplateItemCreate(BaseModel):
    kind: RecurringInvoiceItemKindLiteral
    product_id: uuid.UUID | None = None
    job_id: uuid.UUID | None = None
    description: str = Field(min_length=1)
    sku_or_job_number: str | None = Field(default=None, max_length=64)
    quantity: Decimal = Field(default=Decimal("1"))
    unit_price: Decimal


class RecurringTemplateItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    line_number: int
    kind: RecurringInvoiceItemKindLiteral
    product_id: uuid.UUID | None = None
    job_id: uuid.UUID | None = None
    description: str
    sku_or_job_number: str | None = None
    quantity: Decimal
    unit_price: Decimal


class RecurringTemplateCreate(BaseModel):
    customer_id: uuid.UUID
    name: str = Field(min_length=1, max_length=200)
    cadence_kind: RecurringCadenceKindLiteral
    cadence_interval: int = Field(default=1, ge=1)
    start_at: datetime
    end_at: datetime | None = None
    auto_issue: bool = False
    notes: str | None = None
    discount_amount: Decimal = Field(default=Decimal("0"))
    tax_amount: Decimal = Field(default=Decimal("0"))
    currency: str = Field(default="USD", min_length=3, max_length=3)
    items: list[RecurringTemplateItemCreate] = Field(default_factory=list)


class RecurringTemplateUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    cadence_kind: RecurringCadenceKindLiteral | None = None
    cadence_interval: int | None = Field(default=None, ge=1)
    start_at: datetime | None = None
    end_at: datetime | None = None
    auto_issue: bool | None = None
    notes: str | None = None
    discount_amount: Decimal | None = None
    tax_amount: Decimal | None = None
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    items: list[RecurringTemplateItemCreate] | None = None


class RecurringTemplateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    customer_id: uuid.UUID
    name: str
    cadence_kind: RecurringCadenceKindLiteral
    cadence_interval: int
    start_at: datetime
    end_at: datetime | None = None
    next_issue_at: datetime
    last_issued_at: datetime | None = None
    auto_issue: bool
    state: RecurringTemplateStateLiteral
    notes: str | None = None
    discount_amount: Decimal
    tax_amount: Decimal
    currency: str
    created_by_user_id: uuid.UUID
    created_at: datetime
    updated_at: datetime
    items: list[RecurringTemplateItemResponse] = Field(default_factory=list)


class RecurringTemplateListResponse(BaseModel):
    items: list[RecurringTemplateResponse]
    next_cursor: str | None = None


class RecurringTemplateStateTransitionRequest(BaseModel):
    note: str | None = None


class RecurringInvoiceMaterializeResponse(BaseModel):
    template_id: uuid.UUID
    invoice_id: uuid.UUID
    invoice_number: str
    materialized_at: datetime
    auto_issued: bool
    next_issue_at: datetime | None = None
