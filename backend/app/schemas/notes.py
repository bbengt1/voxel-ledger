"""Pydantic schemas for the notes API surface (Phase 2.6)."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

ALLOWED_ENTITY_KINDS = frozenset({"material", "supply", "rate", "product"})


class NoteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    entity_kind: str
    entity_id: uuid.UUID
    body: str
    author_user_id: uuid.UUID
    is_pinned: bool
    created_at: datetime
    updated_at: datetime


class NoteListResponse(BaseModel):
    items: list[NoteResponse]
    next_cursor: str | None = None


class NoteCreateRequest(BaseModel):
    entity_kind: str = Field(min_length=1, max_length=32)
    entity_id: uuid.UUID
    body: str = Field(min_length=1, max_length=20000)


class NoteUpdateRequest(BaseModel):
    body: str = Field(min_length=1, max_length=20000)
