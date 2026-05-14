"""ORM model for the audit_log read-model (Phase 1.4).

The audit_log is a denormalized projection over the event log: one row per
event, with the actor email/role resolved at projection time and a small
per-event-type ``payload_excerpt`` whitelist. The wildcard audit projection
handler owns this table — see ``app.projections.audit``.

The projection is rebuildable from the event log; ``event_id`` is an
informational FK (ON DELETE SET NULL) but the audit_log row is the
source-of-record for the audit query API.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.core.db import Base

# JSONB on Postgres, plain JSON elsewhere (SQLite tests).
JSONType = JSON().with_variant(JSONB(), "postgresql")
# INET on Postgres, plain string elsewhere.
IpType = String(length=64).with_variant(INET(), "postgresql")


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    event_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("event.id", ondelete="SET NULL"), nullable=True
    )
    event_position: Mapped[int] = mapped_column(BigInteger, nullable=False, unique=True)
    event_type: Mapped[str] = mapped_column(String(255), nullable=False)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )
    actor_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    actor_role: Mapped[str | None] = mapped_column(String(32), nullable=True)
    aggregate_type: Mapped[str] = mapped_column(String(255), nullable=False)
    aggregate_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    ip_address: Mapped[str | None] = mapped_column(IpType, nullable=True)
    payload_excerpt: Mapped[dict[str, Any] | None] = mapped_column(JSONType, nullable=True)
