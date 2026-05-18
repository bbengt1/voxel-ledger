"""Pydantic schemas for the settlement API surface (Phase 9.8, #160)."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class SettlementResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    settlement_number: str
    channel_id: uuid.UUID
    period_start: date
    period_end: date
    gross_amount: Decimal
    fee_amount: Decimal
    refund_amount: Decimal
    adjustment_amount: Decimal
    payout_amount: Decimal
    payout_account_id: uuid.UUID
    filename: str
    imported_at: datetime
    imported_by_user_id: uuid.UUID
    state: str
    posting_journal_entry_id: uuid.UUID | None = None
    notes: str | None = None
    created_at: datetime
    updated_at: datetime


class SettlementListResponse(BaseModel):
    items: list[SettlementResponse]
    next_cursor: str | None = None


class SettlementLineResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    settlement_id: uuid.UUID
    line_number: int
    line_kind: str
    occurred_on: date
    description: str
    external_order_id: str | None = None
    external_txn_id: str | None = None
    amount: Decimal
    state: str
    matched_sale_id: uuid.UUID | None = None
    matched_refund_id: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime


class SettlementWithLinesResponse(BaseModel):
    settlement: SettlementResponse
    lines: list[SettlementLineResponse]


class SettlementLineListResponse(BaseModel):
    items: list[SettlementLineResponse]
    next_cursor: str | None = None
