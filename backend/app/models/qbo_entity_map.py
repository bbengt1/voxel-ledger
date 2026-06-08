"""Mapping between our master-data rows and their QuickBooks Online entities.

Phase 2 (#315, epic #312). One row links a local Customer/Vendor/Product UUID to
the QBO entity it was synced to (Customer/Vendor/Item), carrying the QBO ``Id``
and the latest ``SyncToken`` (QBO's optimistic-concurrency version — required on
every update; a stale token returns error 5010, see Phase-0 findings §2).

Uniqueness both ways: one local row maps to at most one QBO entity, and one QBO
entity is claimed by at most one local row — so re-running an upsert never
creates a duplicate.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, UniqueConstraint, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class QboLocalKind(enum.StrEnum):
    CUSTOMER = "customer"
    VENDOR = "vendor"
    PRODUCT = "product"


QBO_LOCAL_KIND_VALUES: tuple[str, ...] = tuple(m.value for m in QboLocalKind)

QBO_LOCAL_KIND_ENUM = SAEnum(
    *QBO_LOCAL_KIND_VALUES,
    name="qbo_local_kind",
    create_type=False,
)


class QboEntityMap(Base):
    __tablename__ = "qbo_entity_map"
    __table_args__ = (
        UniqueConstraint("local_kind", "local_id", name="ux_qbo_entity_map_local"),
        UniqueConstraint("qbo_entity_type", "qbo_id", name="ux_qbo_entity_map_qbo"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    local_kind: Mapped[str] = mapped_column(QBO_LOCAL_KIND_ENUM, nullable=False)
    local_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    # QBO entity name: "Customer" | "Vendor" | "Item".
    qbo_entity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    qbo_id: Mapped[str] = mapped_column(String(64), nullable=False)
    sync_token: Mapped[str | None] = mapped_column(String(32), nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
