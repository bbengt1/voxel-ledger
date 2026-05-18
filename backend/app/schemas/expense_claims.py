"""Pydantic schemas for the expense-claims API surface (Phase 8.7, #134)."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ExpenseClaimStateLiteral = Literal[
    "draft", "submitted", "approved", "rejected", "reimbursed", "cancelled"
]


# --- Lines ----------------------------------------------------------------


class ExpenseClaimLineCreate(BaseModel):
    """One line on a draft expense claim."""

    expense_category_id: uuid.UUID
    description: str = Field(min_length=1)
    amount: Decimal
    occurred_on: date
    attachment_id: uuid.UUID | None = None
    is_billable: bool = False
    customer_id: uuid.UUID | None = None
    markup_percent: Decimal = Field(default=Decimal("0"))


class ExpenseClaimLineUpdate(BaseModel):
    """PATCH-style — only fields the caller wants to change on a single line."""

    expense_category_id: uuid.UUID | None = None
    description: str | None = None
    amount: Decimal | None = None
    occurred_on: date | None = None
    attachment_id: uuid.UUID | None = None
    is_billable: bool | None = None
    customer_id: uuid.UUID | None = None
    markup_percent: Decimal | None = None


class ExpenseClaimLineResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    line_number: int
    expense_category_id: uuid.UUID
    description: str
    amount: Decimal
    occurred_on: date
    attachment_id: uuid.UUID | None = None
    is_billable: bool
    customer_id: uuid.UUID | None = None
    billed_invoice_item_id: uuid.UUID | None = None
    markup_percent: Decimal


# --- Claim ----------------------------------------------------------------


class ExpenseClaimCreate(BaseModel):
    notes: str | None = None
    currency: str = Field(default="USD", min_length=3, max_length=3)
    lines: list[ExpenseClaimLineCreate] = Field(default_factory=list)


class ExpenseClaimUpdate(BaseModel):
    notes: str | None = None
    currency: str | None = None
    lines: list[ExpenseClaimLineCreate] | None = None


class ExpenseClaimResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    claim_number: str
    submitter_user_id: uuid.UUID
    state: ExpenseClaimStateLiteral
    submitted_at: datetime | None = None
    approved_at: datetime | None = None
    approver_user_id: uuid.UUID | None = None
    rejection_reason: str | None = None
    total_amount: Decimal
    currency: str
    posting_journal_entry_id: uuid.UUID | None = None
    approval_request_id: uuid.UUID | None = None
    reimbursement_payment_id: uuid.UUID | None = None
    notes: str | None = None
    created_at: datetime
    updated_at: datetime
    lines: list[ExpenseClaimLineResponse] = Field(default_factory=list)


class ExpenseClaimListResponse(BaseModel):
    items: list[ExpenseClaimResponse]
    next_cursor: str | None = None


class ExpenseClaimSubmitResponse(BaseModel):
    """Wraps the claim + an optional approval_request_id when the
    threshold gating attached one."""

    claim: ExpenseClaimResponse
    approval_request_id: uuid.UUID | None = None


class ExpenseClaimRejectRequest(BaseModel):
    rejection_reason: str | None = None


class ExpenseClaimApproveRequest(BaseModel):
    note: str | None = None


class ExpenseClaimReimburseRequest(BaseModel):
    bill_payment_id: uuid.UUID
