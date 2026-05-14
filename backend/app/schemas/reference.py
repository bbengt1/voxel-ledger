"""Pydantic schemas for the reference number allocator (Phase 1.3)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class ReferenceSequenceRow(BaseModel):
    """A single ``reference_sequence`` row, surfaced via the admin API."""

    model_config = ConfigDict(from_attributes=True)

    prefix: str
    year: int
    last_value: int
