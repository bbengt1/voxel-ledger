"""ORM model for the ``material`` catalog table (Phase 2.1).

A material is one physical filament/resin SKU. ``current_cost_per_gram``
and ``on_hand_grams`` are read-side caches maintained by the
``material_cost`` projection from the ``inventory.MaterialReceived``
event stream — never mutated directly by service code. The unique
constraint on ``(name, brand, color) where is_archived = false`` keeps
the active catalog free of dupes while allowing archived rows to
coexist with a fresh entry of the same name.

``custom_fields`` is intentionally out of scope here (lands in #2.5).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Material(Base):
    __tablename__ = "material"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    brand: Mapped[str | None] = mapped_column(String(255), nullable=True)
    material_type: Mapped[str] = mapped_column(String(64), nullable=False)
    color: Mapped[str | None] = mapped_column(String(64), nullable=True)

    density_g_per_cm3: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)

    # Read-side caches. Recomputed by the ``material_cost`` projection;
    # never written by service code. Defaults are zero so a freshly
    # created material has well-defined numbers even before the first
    # receipt.
    current_cost_per_gram: Mapped[Decimal] = mapped_column(
        Numeric(18, 6),
        nullable=False,
        default=Decimal("0"),
        server_default="0",
    )
    on_hand_grams: Mapped[Decimal] = mapped_column(
        Numeric(18, 6),
        nullable=False,
        default=Decimal("0"),
        server_default="0",
    )

    is_archived: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
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
