"""ORM model for ``ai_insight_summary`` (Phase 10.7, #182).

A row per requested AI insight. The worker walks oldest-queued first
and flips state ``queued -> running -> ready`` (or ``failed`` with an
error message).

Per agents.md gotcha #1 the ``ai_insight_status`` enum is NOT
pre-created in the migration; ``op.create_table`` auto-creates the PG
type via the column dialect hook. Per gotcha #3 the ORM declares it
with ``SAEnum(..., create_type=False, values_callable=...)``.
"""

from __future__ import annotations

import enum
import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    func,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class AiInsightStatus(enum.StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    READY = "ready"
    FAILED = "failed"


AI_INSIGHT_STATUS_VALUES: tuple[str, ...] = tuple(m.value for m in AiInsightStatus)


AI_INSIGHT_STATUS_ENUM = SAEnum(
    AiInsightStatus,
    name="ai_insight_status",
    values_callable=lambda enum_cls: [m.value for m in enum_cls],
    create_type=False,
)


class AiInsightSummary(Base):
    __tablename__ = "ai_insight_summary"
    __table_args__ = (
        CheckConstraint("period_end >= period_start", name="ck_ai_insight_summary_period_range"),
        Index("ix_ai_insight_summary_scope_status", "scope", "status"),
        Index("ix_ai_insight_summary_status_created_at", "status", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    scope: Mapped[str] = mapped_column(String(64), nullable=False)
    period_start: Mapped[date] = mapped_column(Date(), nullable=False)
    period_end: Mapped[date] = mapped_column(Date(), nullable=False)

    payload: Mapped[dict[str, Any]] = mapped_column(JSON(), nullable=False, default=dict)
    narrative: Mapped[str] = mapped_column(Text(), nullable=False, default="", server_default="")
    model: Mapped[str | None] = mapped_column(String(64), nullable=True)

    status: Mapped[AiInsightStatus] = mapped_column(
        AI_INSIGHT_STATUS_ENUM,
        nullable=False,
        default=AiInsightStatus.QUEUED,
        server_default="queued",
    )
    error: Mapped[str | None] = mapped_column(Text(), nullable=True)

    requested_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


__all__ = [
    "AI_INSIGHT_STATUS_VALUES",
    "AiInsightStatus",
    "AiInsightSummary",
]
