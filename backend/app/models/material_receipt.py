"""ORM model for the ``material_receipt`` table (Phase 2.1).

One row per recorded receipt of material into inventory. The
``unit_cost_at_receipt`` is computed at insert time
(``total_cost / grams``) and stored alongside so historical pricing is
preserved even if a receipt is later corrected or the parent
material's current_cost_per_gram drifts.

CHECK constraints on the table enforce ``grams > 0`` and
``total_cost >= 0`` at the DB layer — defense in depth alongside the
service-layer validation.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class MaterialReceipt(Base):
    __tablename__ = "material_receipt"
    __table_args__ = (
        CheckConstraint("grams > 0", name="ck_material_receipt_grams_positive"),
        CheckConstraint("total_cost >= 0", name="ck_material_receipt_total_cost_non_negative"),
        Index(
            "ix_material_receipt_material_received_at",
            "material_id",
            "received_at",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    material_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("material.id", ondelete="CASCADE"), nullable=False
    )
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    grams: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    total_cost: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    unit_cost_at_receipt: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)

    vendor: Mapped[str | None] = mapped_column(String(255), nullable=True)
    reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
