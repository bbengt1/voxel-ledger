"""Pydantic schemas for the GL detail report (Parity #226)."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel


class LedgerLineResponse(BaseModel):
    journal_entry_id: uuid.UUID
    entry_number: str
    posted_at: datetime
    description: str
    debit: Decimal
    credit: Decimal
    running_balance: Decimal


class LedgerSectionResponse(BaseModel):
    account_id: uuid.UUID
    code: str
    name: str
    type: str
    opening_balance: Decimal
    closing_balance: Decimal
    period_debit: Decimal
    period_credit: Decimal
    lines: list[LedgerLineResponse]


class LedgerDetailResponse(BaseModel):
    date_from: date
    date_to: date
    account_id: uuid.UUID | None = None
    division_id: uuid.UUID | None = None
    sections: list[LedgerSectionResponse]


__all__ = [
    "LedgerDetailResponse",
    "LedgerLineResponse",
    "LedgerSectionResponse",
]
