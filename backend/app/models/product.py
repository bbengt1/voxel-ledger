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
from typing import Any

from sqlalchemy import Boolean, DateTime, Integer, Numeric, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.core.db import Base

_CUSTOM_FIELDS_TYPE = JSON().with_variant(JSONB(), "postgresql")


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

    # Phase 3.3: low-stock alert threshold. NULL = no alert configured.
    low_stock_threshold: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)

    # Assembly-line epic #267 Phase 3: minutes of (operator) labor to
    # assemble one finished product from its parts + supplies. Costed at
    # the cost-engine labor rate and added to the rolled-up product cost.
    assembly_minutes: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )

    is_archived: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )

    # Schema-on-read custom-field payload (Phase 2.5).
    custom_fields: Mapped[dict[str, Any]] = mapped_column(
        _CUSTOM_FIELDS_TYPE,
        nullable=False,
        default=dict,
        server_default=text("'{}'"),
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
