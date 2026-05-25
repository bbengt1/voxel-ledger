"""ORM model for ``saved_report`` (Parity #237).

Per-user filter preset for any report. The ``filters`` column is an
opaque jsonb the backend never interprets; the frontend that owns
the page is the only consumer.

Unique on ``(owner_user_id, report_kind, name)`` so the same user
can't have two "month-end P&L" presets but two users can each have
their own.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class SavedReport(Base):
    __tablename__ = "saved_report"
    __table_args__ = (
        UniqueConstraint(
            "owner_user_id",
            "report_kind",
            "name",
            name="uq_saved_report_owner_kind_name",
        ),
        Index("ix_saved_report_owner_kind", "owner_user_id", "report_kind"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("user.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    report_kind: Mapped[str] = mapped_column(String(64), nullable=False)
    filters: Mapped[dict[str, Any]] = mapped_column(
        JSON(), nullable=False, default=dict, server_default="{}"
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


__all__ = ["SavedReport"]
