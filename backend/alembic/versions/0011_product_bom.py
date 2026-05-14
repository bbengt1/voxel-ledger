"""product_bom_item table (Phase 2.4)

Creates the polymorphic ``product_bom_item`` table that backs the bill-
of-materials feature. ``component_kind`` is a PG ENUM
(``bom_component_kind``) and a CHECK constraint on SQLite. ``component_id``
is intentionally NOT a foreign key — it's polymorphic across material,
supply, and product, and integrity is enforced in
``app.services.bom``.

Round-trips cleanly on both Postgres and SQLite.

Revision ID: 0011_product_bom
Revises: 0010_products
Create Date: 2026-05-14 00:00:02.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011_product_bom"
down_revision: str | None = "0010_products"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


BOM_COMPONENT_KIND_VALUES = ("material", "supply", "product")


def upgrade() -> None:
    # Let SQLAlchemy auto-create the `bom_component_kind` enum via
    # op.create_table. Don't pre-create with checkfirst=True — the dialect
    # hook on op.create_table fires unconditionally (`create_type=False`
    # is not honored) and the second create raises DuplicateObjectError.
    # Same bug pattern that bit 0002_auth and was fixed there too.
    # On SQLite, sa.Enum renders as VARCHAR + CHECK automatically.
    component_kind_col = sa.Column(
        "component_kind",
        sa.Enum(*BOM_COMPONENT_KIND_VALUES, name="bom_component_kind"),
        nullable=False,
    )

    op.create_table(
        "product_bom_item",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "parent_product_id",
            sa.Uuid(),
            sa.ForeignKey("product.id", ondelete="CASCADE"),
            nullable=False,
        ),
        component_kind_col,
        sa.Column("component_id", sa.Uuid(), nullable=False),
        sa.Column("quantity", sa.Numeric(18, 6), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint("quantity > 0", name="ck_product_bom_item_quantity_positive"),
    )

    op.create_index(
        "ix_product_bom_item_parent",
        "product_bom_item",
        ["parent_product_id"],
    )
    op.create_index(
        "ix_product_bom_item_component",
        "product_bom_item",
        ["component_kind", "component_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_product_bom_item_component", table_name="product_bom_item")
    op.drop_index("ix_product_bom_item_parent", table_name="product_bom_item")
    op.drop_table("product_bom_item")

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        sa.Enum(*BOM_COMPONENT_KIND_VALUES, name="bom_component_kind").drop(bind, checkfirst=True)
