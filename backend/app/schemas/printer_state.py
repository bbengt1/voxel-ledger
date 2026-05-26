"""Pydantic schemas for the printer state + history API surface (Phase 5.4).

These types serialize the in-memory ``PrinterState`` cache and the
``printer_history_event`` table. No secrets are surfaced.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

PrinterStateLiteral = Literal[
    "idle",
    "printing",
    "paused",
    "error",
    "disconnected",
]

PrinterEventKindLiteral = Literal[
    "print_started",
    "print_paused",
    "print_resumed",
    "print_completed",
    "print_errored",
    "connected",
    "disconnected",
]


class PrinterTemperatures(BaseModel):
    extruder: float | None = None
    bed: float | None = None


class PrinterStateResponse(BaseModel):
    """Live state snapshot for a single printer."""

    model_config = ConfigDict(from_attributes=True)

    printer_id: uuid.UUID
    state: PrinterStateLiteral
    progress_pct: float | None = Field(default=None, ge=0, le=100)
    elapsed_seconds: int | None = Field(default=None, ge=0)
    remaining_seconds_estimate: int | None = Field(default=None, ge=0)
    current_file: str | None = None
    temperatures: PrinterTemperatures = Field(default_factory=PrinterTemperatures)
    speed_mm_s: float | None = Field(default=None, ge=0)
    flow_mm3_s: float | None = Field(default=None, ge=0)
    filament_used_mm: float | None = Field(default=None, ge=0)
    current_layer: int | None = Field(default=None, ge=0)
    total_layers: int | None = Field(default=None, ge=0)
    last_seen_at: datetime | None = None


class PrinterHistoryEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    printer_id: uuid.UUID
    event_kind: PrinterEventKindLiteral
    occurred_at: datetime
    details: dict[str, Any] | None = None


class PrinterHistoryListResponse(BaseModel):
    items: list[PrinterHistoryEventResponse]
    next_cursor: str | None = None


class MonitorRestartResponse(BaseModel):
    restarted: bool
    printers_monitored: int
