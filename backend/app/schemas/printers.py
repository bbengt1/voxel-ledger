"""Pydantic schemas for the printers API surface (Phase 5.1).

Critical: the response models do NOT include ``moonraker_api_key``
as a raw column. Instead a ``moonraker_api_key_set`` boolean flag tells
the client whether a secret has been stored, and the actual value is
substituted with the sentinel ``"***"`` in any field that surfaces it.
This way the secret is impossible to leak through the OpenAPI surface.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

PrinterTypeLiteral = Literal[
    "prusa_mk4",
    "prusa_mk3s",
    "bambu_x1c",
    "bambu_a1",
    "voron_v2_4",
    "other",
]


class PrinterResponse(BaseModel):
    """Printer response. Excludes ``moonraker_api_key`` by construction —
    the boolean ``moonraker_api_key_set`` is the only signal we surface
    so the UI can decide whether to show "configured" vs "not set"."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    printer_type: PrinterTypeLiteral
    moonraker_url: str | None = None
    moonraker_api_key_set: bool = False
    power_draw_watts: int | None = None
    notes: str | None = None
    is_archived: bool
    created_at: datetime
    updated_at: datetime


class PrinterCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    slug: str = Field(min_length=1, max_length=64)
    printer_type: PrinterTypeLiteral
    moonraker_url: str | None = Field(default=None, max_length=2048)
    moonraker_api_key: str | None = Field(default=None, max_length=4096)
    power_draw_watts: int | None = Field(default=None, ge=0, le=10_000)
    notes: str | None = Field(default=None, max_length=4096)


class PrinterUpdateRequest(BaseModel):
    """PATCH-style — only fields the user wants to change.

    Passing ``moonraker_api_key: null`` clears the stored secret; passing
    a non-null string replaces it.
    """

    name: str | None = Field(default=None, min_length=1, max_length=255)
    slug: str | None = Field(default=None, min_length=1, max_length=64)
    printer_type: PrinterTypeLiteral | None = None
    moonraker_url: str | None = Field(default=None, max_length=2048)
    moonraker_api_key: str | None = Field(default=None, max_length=4096)
    power_draw_watts: int | None = Field(default=None, ge=0, le=10_000)
    notes: str | None = Field(default=None, max_length=4096)


class PrinterListResponse(BaseModel):
    items: list[PrinterResponse]
    next_cursor: str | None = None
