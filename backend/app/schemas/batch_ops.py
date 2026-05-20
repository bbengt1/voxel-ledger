"""Pydantic schemas for batch operations (Phase 11.3, #195)."""

from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, Field


class BatchSpec(BaseModel):
    entity: str = Field(..., min_length=1)
    ids: list[uuid.UUID] = Field(default_factory=list)
    action: str = Field(..., min_length=1)
    params: dict[str, Any] = Field(default_factory=dict)


class BlockerResponse(BaseModel):
    id: uuid.UUID
    reason: str


class BatchPreviewResponse(BaseModel):
    entity: str
    action: str
    matched_count: int
    sample: list[dict[str, Any]]
    blockers: list[BlockerResponse]


class BatchCommitResponse(BaseModel):
    entity: str
    action: str
    applied: int
    skipped: int
    audit_id: uuid.UUID
    blockers: list[BlockerResponse]


__all__ = [
    "BatchCommitResponse",
    "BatchPreviewResponse",
    "BatchSpec",
    "BlockerResponse",
]
