"""Pydantic schemas for the depreciation-run API surface (Phase 9.3, #155)."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel


class DepreciationRunRequest(BaseModel):
    period_end: date


class DepreciationRunResponse(BaseModel):
    period_end: date
    posted_count: int
    failed_count: int
