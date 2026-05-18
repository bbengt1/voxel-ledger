"""Pydantic schemas for the expense-categories API surface (Phase 8.6, #133)."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ExpenseCategoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    name: str
    default_expense_account_id: uuid.UUID
    parent_id: uuid.UUID | None = None
    is_active: bool
    notes: str | None = None
    created_at: datetime
    updated_at: datetime


class ExpenseCategoryCreate(BaseModel):
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=255)
    default_expense_account_id: uuid.UUID
    parent_id: uuid.UUID | None = None
    notes: str | None = Field(default=None, max_length=10_000)


class ExpenseCategoryUpdate(BaseModel):
    code: str | None = Field(default=None, min_length=1, max_length=64)
    name: str | None = Field(default=None, min_length=1, max_length=255)
    default_expense_account_id: uuid.UUID | None = None
    parent_id: uuid.UUID | None = None
    is_active: bool | None = None
    notes: str | None = Field(default=None, max_length=10_000)


class ExpenseCategoryListResponse(BaseModel):
    items: list[ExpenseCategoryResponse]
