"""QBO change-data-capture drift records (#317, epic #312, Phase 4a).

QBO is the system of record. After Phase 3 every posting flows out through the
sync outbox; once a row is ``synced`` we hold a ``qbo_id``. The ``quickbooks_cdc``
worker polls QBO's CDC feed for **external** edits/deletes to those entities —
someone changing a synced Invoice/Payment/JournalEntry directly in QuickBooks.
Such a change is *drift*: our operational record and QBO have diverged.

We never silently re-push (QBO is authoritative); we record the drift here for
admin review. The reconciliation report (Phase 4b) folds open drift into the
"decommission-ready" gate — Phase 5 must not remove the local GL while drift is
unresolved.

One row per ``(entity_type, qbo_id)`` (unique). Repeated detections refresh
``last_detected_at``/``change_type`` and bump ``occurrences`` rather than
inserting duplicates. An operator ``acknowledged`` a row after reconciling it;
a newer external change re-opens it.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, UniqueConstraint, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.core.db import Base

_JSON = JSON().with_variant(JSONB(), "postgresql")


class QboDriftStatus(enum.StrEnum):
    OPEN = "open"  # detected, awaiting operator review
    ACKNOWLEDGED = "acknowledged"  # operator reconciled it; re-opens on a newer change


QBO_DRIFT_STATUS_VALUES: tuple[str, ...] = tuple(m.value for m in QboDriftStatus)

QBO_DRIFT_STATUS_ENUM = SAEnum(
    *QBO_DRIFT_STATUS_VALUES,
    name="qbo_drift_status",
    create_type=False,
)


class QboCdcDrift(Base):
    __tablename__ = "qbo_cdc_drift"
    __table_args__ = (
        UniqueConstraint("entity_type", "qbo_id", name="uq_qbo_cdc_drift_entity"),
        Index("ix_qbo_cdc_drift_status", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    # QBO entity type ("Invoice" | "Payment" | "JournalEntry" | …) + its QBO id.
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    qbo_id: Mapped[str] = mapped_column(String(64), nullable=False)
    # Latest observed external change.
    change_type: Mapped[str] = mapped_column(String(16), nullable=False)  # updated|deleted
    # Resolved back to the local posting that produced this QBO entity (via the
    # synced outbox row). Nullable: a drift entity may not match a synced row.
    local_kind: Mapped[str | None] = mapped_column(String(64), nullable=True)
    local_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    occurrences: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    status: Mapped[str] = mapped_column(
        QBO_DRIFT_STATUS_ENUM, nullable=False, server_default="open"
    )
    # Snapshot of the CDC object (or the salient fields) for the admin drilldown.
    detail: Mapped[dict | None] = mapped_column(_JSON, nullable=True)
    first_detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    acknowledged_by_user_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
