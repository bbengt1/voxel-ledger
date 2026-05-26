"""Pydantic schemas for deposit slips (Parity #235)."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

DepositSlipStateLiteral = Literal["draft", "deposited", "reconciled"]


class DepositSlipBuildRequest(BaseModel):
    payment_ids: list[uuid.UUID] = Field(..., min_length=1)
    bank_account_id: uuid.UUID
    deposit_date: date


class DepositSlipItemResponse(BaseModel):
    id: uuid.UUID
    payment_id: uuid.UUID
    amount: Decimal


class DepositSlipResponse(BaseModel):
    id: uuid.UUID
    slip_number: str
    bank_account_id: uuid.UUID
    deposit_date: date
    total_amount: Decimal
    state: DepositSlipStateLiteral
    posting_journal_entry_id: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime


class UndepositedPaymentResponse(BaseModel):
    id: uuid.UUID
    payment_number: str
    customer_id: uuid.UUID
    amount: Decimal
    method: str
    received_at: datetime
    reference: str | None = None


__all__ = [
    "DepositSlipBuildRequest",
    "DepositSlipItemResponse",
    "DepositSlipResponse",
    "DepositSlipStateLiteral",
    "UndepositedPaymentResponse",
]
