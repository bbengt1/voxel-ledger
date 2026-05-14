"""Pydantic schemas for the event log API surface."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class EventCreate(BaseModel):
    """Input shape for ``EventStore.append``.

    Hashes and ``position`` are computed by the store, not the caller.
    ``recorded_at`` is set by the DB default. ``occurred_at`` and
    ``correlation_id`` are required because they belong to the business
    event, not the persistence layer.
    """

    type: str
    aggregate_type: str
    aggregate_id: uuid.UUID
    payload: dict[str, Any]
    occurred_at: datetime
    correlation_id: uuid.UUID
    causation_id: uuid.UUID | None = None
    actor_user_id: uuid.UUID | None = None
    schema_version: int = 1


class EventRead(BaseModel):
    """Hydrated event row, returned to callers and used by the verifier."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    position: int
    type: str
    aggregate_type: str
    aggregate_id: uuid.UUID
    payload: dict[str, Any]
    occurred_at: datetime
    recorded_at: datetime
    actor_user_id: uuid.UUID | None
    correlation_id: uuid.UUID
    causation_id: uuid.UUID | None
    prev_event_hash: str
    event_hash: str
    schema_version: int


class VerifyChainResponse(BaseModel):
    """Result of ``GET /admin/events/verify-chain``.

    ``ok=True`` means every event's recomputed hash matches what we stored
    and every ``prev_event_hash`` matches the previous row's
    ``event_hash``. ``broken_at_position`` is the first position where
    the chain fails.
    """

    ok: bool
    last_position: int | None = Field(
        default=None,
        description="Last position the verifier successfully validated.",
    )
    broken_at_position: int | None = Field(
        default=None,
        description="First position where verification failed (None if ok=True).",
    )
    events_checked: int = 0
