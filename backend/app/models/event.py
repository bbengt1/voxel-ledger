"""ORM model for the append-only domain event log (Phase 1.1).

The event log is the source of truth for accounting state. Every row is a
business event; projections, balances, and reports are derived from it.

The table is append-only by design. Postgres enforces this with a
``BEFORE UPDATE OR DELETE`` trigger added in the alembic migration. SQLite
(tests) does not enforce it — application code never attempts to mutate
event rows anyway, and the immutability test only runs on PG.

The hash chain (``prev_event_hash`` → ``event_hash``) lets us detect
tampering or partial writes during a long-running incident. Verification
is exposed via the ``GET /api/v1/admin/events/verify-chain`` endpoint.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.core.db import Base

# JSONB on Postgres, plain JSON elsewhere (SQLite tests).
JSONType = JSON().with_variant(JSONB(), "postgresql")


class Event(Base):
    __tablename__ = "event"

    # UUID identity is what callers reference. ``position`` is the strictly
    # monotonic stream cursor — projections read by ``position`` order.
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    position: Mapped[int] = mapped_column(
        BigInteger, nullable=False, unique=True, autoincrement=True, index=True
    )

    type: Mapped[str] = mapped_column(String(255), nullable=False)
    aggregate_type: Mapped[str] = mapped_column(String(255), nullable=False)
    aggregate_id: Mapped[uuid.UUID] = mapped_column(nullable=False)

    payload: Mapped[dict] = mapped_column(JSONType, nullable=False)

    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )

    correlation_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    causation_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)

    # SHA-256 hex digest of the previous row's canonical bytes (or 64 zeros
    # for the genesis event). The current row's ``event_hash`` is computed
    # over canonical bytes including ``prev_event_hash``, so the chain is
    # tamper-evident.
    prev_event_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    event_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)

    # Bump this when a payload model is upcasted. TODO(phase-1.2): plug in
    # the upcaster registry here when concrete event types arrive.
    schema_version: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="1", default=1
    )
