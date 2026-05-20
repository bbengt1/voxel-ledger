"""Pydantic schemas for the AI-insights API (Phase 10.7, #182)."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

AiInsightStatusLiteral = Literal["queued", "running", "ready", "failed"]


class AiInsightRequest(BaseModel):
    scope: str
    period_start: date
    period_end: date


class AiInsightSummaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    scope: str
    period_start: date
    period_end: date
    payload: dict[str, Any]
    narrative: str
    model: str | None = None
    status: AiInsightStatusLiteral
    error: str | None = None
    requested_by_user_id: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime
