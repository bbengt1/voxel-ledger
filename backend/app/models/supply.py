"""ORM model for the ``supply`` catalog table (Phase 2.2).

A supply is a unit-cost consumable (e.g. resin cleaner, packaging) that
isn't tracked by weighted-average cost the way materials are. The
``unit_cost`` column is set directly on create/update — no receipts
sub-resource. ``on_hand`` is a read-side cache that future Phase 3
inventory transactions will own; service code only seeds the initial
balance via the create payload.

Like ``Material``, the partial unique constraint on ``(name, vendor)
WHERE is_archived = false`` keeps the active catalog free of dupes while
letting archived rows coexist with fresh same-named entries.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, Index, Numeric, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Supply(Base):
    __tablename__ = "supply"
    __table_args__ = (
        # Partial unique index: only active (non-archived) rows enforce
        # uniqueness on (name, vendor).
        Index(
            "ux_supply_name_vendor_active",
            "name",
            "vendor",
            unique=True,
            sqlite_where=text("is_archived = 0"),
            postgresql_where=text("is_archived = false"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    unit: Mapped[str] = mapped_column(String(32), nullable=False)
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    vendor: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Read-side cache. Phase 3 inventory transactions will own this;
    # service code only writes the starting balance on create.
    on_hand: Mapped[Decimal] = mapped_column(
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
