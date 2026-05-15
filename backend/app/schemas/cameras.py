"""Pydantic schemas for the cameras API surface (Phase 5.1).

Critical: the response models do NOT include ``password_secret`` as a
raw column. Instead a ``password_secret_set`` boolean flag tells the
client whether a secret has been stored.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

CameraKindLiteral = Literal["wyze", "rtsp", "go2rtc", "other"]


class CameraResponse(BaseModel):
    """Camera response. Excludes ``password_secret`` by construction."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    printer_id: uuid.UUID
    kind: CameraKindLiteral
    snapshot_url: str
    username: str | None = None
    password_secret_set: bool = False
    is_active: bool
    created_at: datetime
    updated_at: datetime


class CameraConfigRequest(BaseModel):
    """Used for both POST (set/replace) and the body of PUT/PATCH-style
    upserts. ``password_secret`` is write-only — never echoed back."""

    kind: CameraKindLiteral
    snapshot_url: str = Field(min_length=1, max_length=2048)
    username: str | None = Field(default=None, max_length=255)
    password_secret: str | None = Field(default=None, max_length=4096)
    is_active: bool = True
