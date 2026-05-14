"""ORM model for the ``product_bom_item`` table (Phase 2.4).

One row per component slot in a parent product's bill-of-materials.
``component_kind`` is a polymorphic discriminator; ``component_id`` is
NOT an FK because it points into one of three different tables
(``material``, ``supply``, ``product``). Integrity is enforced at the
service layer.

The Phase 2.4 cost-rollup projection lives in
``app.projections.product_cost`` and walks this table to recompute
``product.unit_cost_cached``.
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

# Allowed values for the polymorphic component_kind enum. Mirrored in the
# Alembic migration (PG ENUM ``bom_component_kind`` / SQLite CHECK).
COMPONENT_KIND_MATERIAL = "material"
COMPONENT_KIND_SUPPLY = "supply"
COMPONENT_KIND_PRODUCT = "product"
COMPONENT_KIND_VALUES: tuple[str, ...] = (
    COMPONENT_KIND_MATERIAL,
    COMPONENT_KIND_SUPPLY,
    COMPONENT_KIND_PRODUCT,
)


class ProductBomItem(Base):
    __tablename__ = "product_bom_item"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_product_bom_item_quantity_positive"),
        Index("ix_product_bom_item_parent", "parent_product_id"),
        Index(
            "ix_product_bom_item_component",
            "component_kind",
            "component_id",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    parent_product_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("product.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Polymorphic discriminator. PG: ENUM ``bom_component_kind``. SQLite:
    # plain string with a CHECK constraint added by the migration.
    component_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    # Polymorphic reference. No FK — see module docstring.
    component_id: Mapped[uuid.UUID] = mapped_column(nullable=False)

    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text(), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
