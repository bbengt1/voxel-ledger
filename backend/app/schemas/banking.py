"""Pydantic schemas for the banking API surface (Phase 8.9, #136)."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

# --- Mappings --------------------------------------------------------------


class BankImportMappingCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    account_id: uuid.UUID
    file_kind: str = Field(pattern="^(csv|ofx)$")
    column_map: dict[str, Any] = Field(default_factory=dict)
    date_format: str | None = Field(default=None, max_length=64)
    delimiter: str = Field(default=",", max_length=4)
    has_header: bool = True
    encoding: str = Field(default="utf-8", max_length=32)
    amount_sign: str = Field(pattern="^(signed_amount|debit_credit_columns|inflow_outflow)$")
    notes: str | None = Field(default=None, max_length=10_000)


class BankImportMappingUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    column_map: dict[str, Any] | None = None
    date_format: str | None = Field(default=None, max_length=64)
    delimiter: str | None = Field(default=None, max_length=4)
    has_header: bool | None = None
    encoding: str | None = Field(default=None, max_length=32)
    amount_sign: str | None = Field(
        default=None,
        pattern="^(signed_amount|debit_credit_columns|inflow_outflow)$",
    )
    notes: str | None = Field(default=None, max_length=10_000)
    is_active: bool | None = None


class BankImportMappingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    account_id: uuid.UUID
    file_kind: str
    column_map: dict[str, Any]
    date_format: str | None = None
    delimiter: str
    has_header: bool
    encoding: str
    amount_sign: str
    is_active: bool
    notes: str | None = None
    created_by_user_id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class BankImportMappingListResponse(BaseModel):
    items: list[BankImportMappingResponse]


# --- Runs ------------------------------------------------------------------


class BankImportRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    account_id: uuid.UUID
    mapping_id: uuid.UUID | None = None
    filename: str
    imported_at: datetime
    imported_by_user_id: uuid.UUID
    row_count: int
    inserted_count: int
    duplicate_count: int
    error_count: int
    notes: str | None = None


class BankImportRunListResponse(BaseModel):
    items: list[BankImportRunResponse]


# --- Transactions ----------------------------------------------------------


class BankTransactionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    account_id: uuid.UUID
    import_run_id: uuid.UUID | None = None
    imported_at: datetime
    occurred_on: date
    description: str
    memo: str | None = None
    amount: Decimal
    running_balance: Decimal | None = None
    fitid: str | None = None
    external_hash: str
    state: str
    matched_journal_line_id: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime


class BankTransactionListResponse(BaseModel):
    items: list[BankTransactionResponse]
    next_cursor: str | None = None
