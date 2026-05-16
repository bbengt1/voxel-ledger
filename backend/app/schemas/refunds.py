"""Pydantic schemas for the refunds API surface (Phase 6.5, #97)."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

RefundKindLiteral = Literal["full", "partial", "store_credit", "marketplace_initiated"]
RefundStateLiteral = Literal["pending_approval", "approved", "posted", "rejected", "cancelled"]


# --- Items -----------------------------------------------------------------


class RefundItemCreate(BaseModel):
    """One line on a draft refund.

    ``unit_amount`` is the refund value per unit (typically the
    originating ``sale_item.unit_price``; the service does not enforce
    that — partial-price refunds are allowed). ``extended_amount`` is
    computed by the service as ``quantity * unit_amount``.
    """

    sale_item_id: uuid.UUID
    quantity: Decimal
    unit_amount: Decimal


class RefundItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    sale_item_id: uuid.UUID
    quantity: Decimal
    unit_amount: Decimal
    extended_amount: Decimal


# --- Refund ----------------------------------------------------------------


class RefundCreate(BaseModel):
    sale_id: uuid.UUID
    kind: RefundKindLiteral
    reason_code: str = Field(min_length=1, max_length=64)
    notes: str | None = None
    restock_inventory: bool = True
    items: list[RefundItemCreate] = Field(default_factory=list)


class RefundResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    refund_number: str
    sale_id: uuid.UUID
    kind: RefundKindLiteral
    state: RefundStateLiteral
    total_amount: Decimal
    restock_inventory: bool
    reason_code: str
    notes: str | None = None
    created_by_user_id: uuid.UUID
    approved_by_user_id: uuid.UUID | None = None
    approval_request_id: uuid.UUID | None = None
    posting_journal_entry_id: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime
    items: list[RefundItemResponse] = Field(default_factory=list)


class RefundListResponse(BaseModel):
    items: list[RefundResponse]
    next_cursor: str | None = None


class RefundApprovalDecision(BaseModel):
    """Body for approve / reject. ``note`` becomes the decision_note on
    the linked ApprovalRequest if one was created."""

    note: str | None = None


class RefundCreateResponse(BaseModel):
    """Wraps the refund + an optional approval_request_id for the 202
    pending-approval case. The router decides 201 vs 202 by inspecting
    state == pending_approval."""

    refund: RefundResponse
    approval_request_id: uuid.UUID | None = None
