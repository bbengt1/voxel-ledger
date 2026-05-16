"""Pydantic schemas for the email-messages API (Phase 7.7, #115)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

EmailKindLiteral = Literal[
    "quote",
    "invoice",
    "statement",
    "recurring_invoice",
    "password_reset",
    "generic",
]

EmailStateLiteral = Literal["queued", "sending", "sent", "failed", "bounced"]


class EmailAttachmentRef(BaseModel):
    filename: str
    storage_key: str


class EmailMessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    kind: EmailKindLiteral
    subject_kind: str | None
    subject_id: uuid.UUID | None
    to_address: str
    from_address: str
    subject: str
    body_html_storage_key: str
    attachments_json: list[EmailAttachmentRef] | None
    state: EmailStateLiteral
    attempts: int
    next_retry_at: datetime | None
    last_error: str | None
    provider_message_id: str | None
    sent_at: datetime | None
    created_at: datetime
    updated_at: datetime


class EmailMessageListResponse(BaseModel):
    items: list[EmailMessageResponse]


class SendStatementRequest(BaseModel):
    include_paid: bool = False
