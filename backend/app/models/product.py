"""ORM model for the ``product`` catalog table (Phase 2.3).

A product is a sellable SKU. ``sku`` is unique and is normally allocated
by ``ReferenceNumberService`` as ``PROD-YYYY-NNNN``; the caller may
supply a manual SKU instead. ``upc`` is optional and has a partial
unique index so multiple products may have NULL UPCs without colliding,
while non-NULL UPCs must be unique.

``unit_cost_cached`` is reserved for Phase 2.4's BOM rollup — created
here as a nullable column but neither set nor read by this issue.

``custom_fields`` is intentionally out of scope here (lands in #2.5).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Product(Base):
    __tablename__ = "product"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    sku: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    upc: Mapped[str | None] = mapped_column(String(64), nullable=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text(), nullable=True)

    unit_price: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    # Reserved for the Phase 2.4 BOM rollup. Service code in this issue
    # never reads or writes this column.
    unit_cost_cached: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    weight_grams: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    category: Mapped[str | None] = mapped_column(String(64), nullable=True)

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
