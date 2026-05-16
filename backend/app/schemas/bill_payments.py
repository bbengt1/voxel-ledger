"""Pydantic schemas for bill payments + applications (Phase 8.3, #130)."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

BillPaymentMethodLiteral = Literal["cash", "check", "ach", "wire", "card", "other"]
BillPaymentStateLiteral = Literal["pending", "posted", "bounced", "cancelled"]


class BillPaymentApplicationInput(BaseModel):
    bill_id: uuid.UUID
    amount_applied: Decimal


class BillPaymentCreate(BaseModel):
    vendor_id: uuid.UUID
    method: BillPaymentMethodLiteral
    amount: Decimal
    occurred_at: datetime | None = None
    reference_number: str | None = Field(default=None, max_length=64)
    notes: str | None = None
    applications: list[BillPaymentApplicationInput] = Field(default_factory=list)


class BillPaymentApplicationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    bill_id: uuid.UUID
    amount_applied: Decimal
    created_at: datetime
    updated_at: datetime


class BillPaymentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    payment_number: str
    vendor_id: uuid.UUID
    method: BillPaymentMethodLiteral
    amount: Decimal
    occurred_at: datetime
    reference_number: str | None = None
    notes: str | None = None
    state: BillPaymentStateLiteral
    posting_journal_entry_id: uuid.UUID | None = None
    created_by_user_id: uuid.UUID
    created_at: datetime
    updated_at: datetime
    applications: list[BillPaymentApplicationResponse] = Field(default_factory=list)


class BillPaymentListResponse(BaseModel):
    items: list[BillPaymentResponse]
    next_cursor: str | None = None


class BillPaymentTransitionRequest(BaseModel):
    note: str | None = None
