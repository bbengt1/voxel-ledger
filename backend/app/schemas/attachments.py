"""Pydantic schemas for the attachments API surface (Phase 2.6)."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AttachmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    entity_kind: str
    entity_id: uuid.UUID
    filename: str
    mime_type: str
    byte_size: int
    uploaded_by_user_id: uuid.UUID
    is_archived: bool
    created_at: datetime
    updated_at: datetime


class AttachmentListResponse(BaseModel):
    items: list[AttachmentResponse]
    next_cursor: str | None = None
