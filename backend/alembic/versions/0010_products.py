"""products catalog table

Creates the catalog ``product`` table plus indexes (including a partial
unique on ``upc`` so multiple NULL UPCs may coexist while non-NULL UPCs
must be unique).

``unit_cost_cached`` is created nullable here; the Phase 2.4 BOM rollup
will populate it. Phase 2.3 service code neither reads nor writes the
column.

Revision ID: 0010_products
Revises: 0008_materials
Create Date: 2026-05-14 00:00:00.000000

The parallel #38 Supplies & Rates migration takes the 0009 slot.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010_products"
down_revision: str | None = "0009_supplies_rates"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "product",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("sku", sa.String(length=64), nullable=False, unique=True),
        sa.Column("upc", sa.String(length=64), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("unit_price", sa.Numeric(18, 6), nullable=False),
        sa.Column("unit_cost_cached", sa.Numeric(18, 6), nullable=True),
        sa.Column("weight_grams", sa.Numeric(18, 6), nullable=True),
        sa.Column("category", sa.String(length=64), nullable=True),
        sa.Column(
            "is_archived",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
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
    )

    # Partial unique on UPC — NULLs don't collide, non-NULLs must be
    # unique. Works on both Postgres and SQLite (≥ 3.8).
    op.create_index(
        "ux_product_upc_not_null",
        "product",
        ["upc"],
        unique=True,
        sqlite_where=sa.text("upc IS NOT NULL"),
        postgresql_where=sa.text("upc IS NOT NULL"),
    )

    op.create_index("ix_product_category", "product", ["category"])
    op.create_index("ix_product_is_archived", "product", ["is_archived"])
    op.create_index(
        "ix_product_created_at_id",
        "product",
        ["created_at", "id"],
    )


def downgrade() -> None:
    op.drop_index("ix_product_created_at_id", table_name="product")
    op.drop_index("ix_product_is_archived", table_name="product")
    op.drop_index("ix_product_category", table_name="product")
    op.drop_index("ux_product_upc_not_null", table_name="product")
    op.drop_table("product")
