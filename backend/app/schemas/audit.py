"""Pydantic schemas for the audit-log query API (Phase 1.4)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class AuditLogRow(BaseModel):
    """One row in the audit_log read model, as returned by the query API."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    event_id: uuid.UUID | None
    event_position: int
    event_type: str
    actor_user_id: uuid.UUID | None
    actor_email: str | None
    actor_role: str | None
    aggregate_type: str
    aggregate_id: uuid.UUID
    occurred_at: datetime
    summary: str
    ip_address: str | None
    payload_excerpt: dict[str, Any] | None


class AuditLogResponse(BaseModel):
    """Paginated list response. ``next_cursor`` is an opaque base64 token
    that, when passed back, resumes pagination just past the last returned
    row. ``null`` when the list is exhausted."""

    items: list[AuditLogRow]
    next_cursor: str | None = None
