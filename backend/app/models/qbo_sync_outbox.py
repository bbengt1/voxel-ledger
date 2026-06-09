"""Transactional outbox for pushing local postings to QuickBooks (#316, epic #312).

Phase 3 foundation. When ``quickbooks.enabled`` is on, each posting site enqueues
one ``qbo_sync_outbox`` row **in the same transaction** as the business operation
(so a rolled-back operation leaves no orphan sync row). The ``quickbooks_sync``
worker drains pending rows: it builds the QBO document from ``payload`` (role-
tagged lines resolved via the account map) and pushes it, recording the returned
QBO id. Failures back off with jitter and dead-letter after the retry window.

``request_id`` is a stable UUID assigned at enqueue and reused on every retry —
QBO's canonical idempotency key (Phase-0), so a retried push never duplicates.

``payload`` is a builder-agnostic spec (JSON), e.g. for a journal entry::

    {"lines": [{"role": "revenue", "posting": "credit", "amount": "10.00"},
               {"role": "accounts_receivable", "posting": "debit", "amount": "10.00"}],
     "doc_number": "INV-2026-0001", "private_note": "..."}
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, Text, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.core.db import Base

_JSON = JSON().with_variant(JSONB(), "postgresql")


class QboSyncStatus(enum.StrEnum):
    PENDING = "pending"  # queued / awaiting (first attempt or a backoff retry)
    SYNCED = "synced"  # pushed to QBO successfully
    FAILED = "failed"  # permanent error (e.g. bad payload / 4xx) — manual retry only
    DEAD = "dead"  # exhausted the retry window — manual retry only


QBO_SYNC_STATUS_VALUES: tuple[str, ...] = tuple(m.value for m in QboSyncStatus)

QBO_SYNC_STATUS_ENUM = SAEnum(
    *QBO_SYNC_STATUS_VALUES,
    name="qbo_sync_status",
    create_type=False,
)


class QboSyncOutbox(Base):
    __tablename__ = "qbo_sync_outbox"
    __table_args__ = (
        Index("ix_qbo_sync_outbox_due", "status", "next_attempt_at"),
        Index("ix_qbo_sync_outbox_source", "kind", "local_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    # Source posting kind, e.g. "sale" | "invoice" | "payment" | "bill" |
    # "journal_entry" | "depreciation" | …. A builder is registered per kind.
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    local_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    op: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="post"
    )  # post|reverse
    status: Mapped[str] = mapped_column(
        QBO_SYNC_STATUS_ENUM, nullable=False, server_default="pending"
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    # Phase-0 idempotency key — stable across retries.
    request_id: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict] = mapped_column(_JSON, nullable=False)
    qbo_entity_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    qbo_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text(), nullable=True)
    next_attempt_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
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
