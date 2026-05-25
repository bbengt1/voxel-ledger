"""Pydantic schemas for saved reports (Parity #237)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class SavedReportCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    report_kind: str = Field(..., min_length=1, max_length=64)
    filters: dict[str, Any] = Field(default_factory=dict)


class SavedReportUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    filters: dict[str, Any] | None = None


class SavedReportRead(BaseModel):
    id: uuid.UUID
    name: str
    report_kind: str
    filters: dict[str, Any]
    created_at: datetime
    updated_at: datetime


__all__ = ["SavedReportCreate", "SavedReportRead", "SavedReportUpdate"]
