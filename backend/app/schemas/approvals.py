"""Pydantic schemas for the approval-workflow API surface (Phase 4.4, #67)."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

ApprovalStateLiteral = Literal["pending", "approved", "rejected", "cancelled"]


class ApprovalRequestResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    request_type: str
    subject_kind: str
    subject_id: uuid.UUID
    requested_by_user_id: uuid.UUID
    requested_at: datetime
    state: ApprovalStateLiteral
    decided_by_user_id: uuid.UUID | None = None
    decided_at: datetime | None = None
    decision_note: str | None = None
    # The endpoint surfaces the full payload to authorized callers; only
    # the audit log restricts it.
    payload: dict[str, Any]
    threshold_amount: Decimal | None = None
    consumed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class ApprovalRequestListResponse(BaseModel):
    items: list[ApprovalRequestResponse]
    next_cursor: str | None = None


class ApprovalActionRequest(BaseModel):
    """Used for approve / reject. ``decision_note`` is optional free text."""

    decision_note: str | None = Field(default=None, max_length=4096)


class ApprovalCancelRequest(BaseModel):
    """Cancel uses ``reason`` for surface symmetry; stored as decision_note."""

    reason: str | None = Field(default=None, max_length=4096)


class JournalEntryPendingApprovalResponse(BaseModel):
    """Returned from POST /accounting/entries with HTTP 202 when an entry
    crosses the configured approval threshold."""

    status: Literal["pending_approval"] = "pending_approval"
    approval_request_id: uuid.UUID
