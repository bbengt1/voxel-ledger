"""Approval-workflow event types (Phase 4.4, #67).

Generic approval queue events. Consumers include journal entries (above
threshold), future refund flows, period-close finalization, etc.

Payloads use ``extra="forbid"``. We intentionally do NOT include the full
proposed payload — only a short ``payload_summary`` string — to keep
sensitive request contents out of the event log (and therefore the audit
projection). The full payload lives on the ``approval_request`` row.
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict

from app.events.registry import register_event

# Approval-request aggregate. Each request is its own aggregate.
AGGREGATE_TYPE_APPROVAL_REQUEST: str = "approval_request"


class _ApprovalsPayloadBase(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ApprovalRequestedPayload(_ApprovalsPayloadBase):
    request_id: uuid.UUID
    request_type: str
    subject_kind: str
    subject_id: uuid.UUID
    requested_by_user_id: uuid.UUID
    # ~100 chars; never the full payload (which could carry sensitive data).
    payload_summary: str
    threshold_amount: str | None = None


class ApprovalApprovedPayload(_ApprovalsPayloadBase):
    request_id: uuid.UUID
    approver_user_id: uuid.UUID
    # First 100 chars of the decision note, if any.
    decision_note_preview: str | None = None


class ApprovalRejectedPayload(_ApprovalsPayloadBase):
    request_id: uuid.UUID
    approver_user_id: uuid.UUID
    decision_note_preview: str | None = None


class ApprovalCancelledPayload(_ApprovalsPayloadBase):
    request_id: uuid.UUID
    cancelled_by_user_id: uuid.UUID


TYPE_APPROVAL_REQUESTED = "platform.ApprovalRequested"
TYPE_APPROVAL_APPROVED = "platform.ApprovalApproved"
TYPE_APPROVAL_REJECTED = "platform.ApprovalRejected"
TYPE_APPROVAL_CANCELLED = "platform.ApprovalCancelled"


register_event(TYPE_APPROVAL_REQUESTED, ApprovalRequestedPayload)
register_event(TYPE_APPROVAL_APPROVED, ApprovalApprovedPayload)
register_event(TYPE_APPROVAL_REJECTED, ApprovalRejectedPayload)
register_event(TYPE_APPROVAL_CANCELLED, ApprovalCancelledPayload)
