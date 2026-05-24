"""Pydantic schemas for worker run-state (Issue #220)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

WorkerRunStatusLiteral = Literal["ok", "failed", "running"]


class WorkerRunStateRead(BaseModel):
    job_name: str
    cron: str
    description: str
    last_started_at: datetime | None = None
    last_finished_at: datetime | None = None
    last_status: WorkerRunStatusLiteral | None = None
    last_error: str | None = None
    last_processed: int = 0
    last_duration_ms: int | None = None
    updated_at: datetime | None = None


__all__ = ["WorkerRunStateRead", "WorkerRunStatusLiteral"]
