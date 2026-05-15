"""Pydantic schemas for the journal-entries API surface (Phase 4.2, #65)."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.accounts import AccountTypeLiteral


class JournalLineCreate(BaseModel):
    account_id: uuid.UUID
    division_id: uuid.UUID | None = None
    debit: Decimal = Field(default=Decimal("0"))
    credit: Decimal = Field(default=Decimal("0"))
    line_number: int = Field(ge=0)
    memo: str | None = Field(default=None, max_length=4096)

    @field_validator("debit", "credit")
    @classmethod
    def _non_negative(cls, value: Decimal) -> Decimal:
        if value < 0:
            raise ValueError("debit and credit must be non-negative")
        return value


class JournalEntryCreate(BaseModel):
    description: str = Field(min_length=1, max_length=4096)
    posted_at: datetime
    lines: list[JournalLineCreate] = Field(min_length=2)


class JournalEntryReverseRequest(BaseModel):
    description: str | None = Field(default=None, max_length=4096)


class JournalLineResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    account_id: uuid.UUID
    account_code: str
    account_name: str
    account_type: AccountTypeLiteral
    division_id: uuid.UUID | None = None
    debit: Decimal
    credit: Decimal
    line_number: int
    memo: str | None = None


class JournalEntryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    entry_number: str
    posted_at: datetime
    period_id: uuid.UUID
    description: str
    actor_user_id: uuid.UUID
    is_reversed: bool
    reversal_of_entry_id: uuid.UUID | None = None
    created_at: datetime
    lines: list[JournalLineResponse]


class JournalEntryListResponse(BaseModel):
    items: list[JournalEntryResponse]
    next_cursor: str | None = None


class AccountBalanceResponse(BaseModel):
    account_id: uuid.UUID
    account_code: str
    account_name: str
    account_type: AccountTypeLiteral
    total_debits: Decimal
    total_credits: Decimal
    balance: Decimal
    updated_at: datetime


class AccountBalanceListResponse(BaseModel):
    items: list[AccountBalanceResponse]
    next_cursor: str | None = None
