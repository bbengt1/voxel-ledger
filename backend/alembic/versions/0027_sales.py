"""sale + sale_item tables (Phase 6.2, #94)

Creates the ``sale`` and ``sale_item`` tables plus the ``sale_state`` and
``sale_item_kind`` PG enums.

Per ops convention (see #49 / agents.md PG strict-typing gotcha #1), the
enums are NOT pre-created. ``op.create_table`` autocreates the PG types
via the columns' dialect hook; on SQLite the same ``sa.Enum`` renders as
``VARCHAR + CHECK``.

A CHECK constraint on ``sale_item`` enforces exactly one of
``product_id`` / ``job_id`` is set OR both are null (kind=manual). The
service layer also guards this — DB constraint is belt-and-suspenders.

Revision ID: 0027_sales
Revises: 0026_sales_channels
Create Date: 2026-05-15 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0027_sales"
down_revision: str | None = "0026_sales_channels"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


SALE_STATE_VALUES = (
    "draft",
    "confirmed",
    "fulfilled",
    "cancelled",
)

SALE_ITEM_KIND_VALUES = (
    "product",
    "job",
    "manual",
)


def upgrade() -> None:
    sale_state_enum = sa.Enum(*SALE_STATE_VALUES, name="sale_state")
    sale_item_kind_enum = sa.Enum(*SALE_ITEM_KIND_VALUES, name="sale_item_kind")

    op.create_table(
        "sale",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("sale_number", sa.String(length=32), nullable=False, unique=True),
        sa.Column(
            "channel_id",
            sa.Uuid(),
            sa.ForeignKey("sales_channel.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("external_order_id", sa.Text(), nullable=True),
        sa.Column("customer_name", sa.String(length=255), nullable=False),
        sa.Column("customer_email", sa.String(length=255), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "subtotal",
            sa.Numeric(18, 6),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "discount_amount",
            sa.Numeric(18, 6),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "shipping_amount",
            sa.Numeric(18, 6),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "tax_amount",
            sa.Numeric(18, 6),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "channel_fee_amount",
            sa.Numeric(18, 6),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "total_amount",
            sa.Numeric(18, 6),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "state",
            sale_state_enum,
            nullable=False,
            server_default="draft",
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_by_user_id",
            sa.Uuid(),
            sa.ForeignKey("user.id", ondelete="RESTRICT"),
            nullable=False,
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

    op.create_index("ix_sale_state", "sale", ["state"])
    op.create_index("ix_sale_channel_id", "sale", ["channel_id"])
    op.create_index("ix_sale_occurred_at", "sale", ["occurred_at"])
    op.create_index("ix_sale_created_at_id", "sale", ["created_at", "id"])

    op.create_table(
        "sale_item",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "sale_id",
            sa.Uuid(),
            sa.ForeignKey("sale.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("line_number", sa.Integer(), nullable=False),
        sa.Column("kind", sale_item_kind_enum, nullable=False),
        sa.Column(
            "product_id",
            sa.Uuid(),
            sa.ForeignKey("product.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "job_id",
            sa.Uuid(),
            sa.ForeignKey("job.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("sku_or_job_number", sa.String(length=64), nullable=True),
        sa.Column(
            "quantity",
            sa.Numeric(18, 6),
            nullable=False,
            server_default=sa.text("1"),
        ),
        sa.Column("unit_price", sa.Numeric(18, 6), nullable=False),
        sa.Column("extended_amount", sa.Numeric(18, 6), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("sale_id", "line_number", name="uq_sale_item_sale_line"),
        sa.CheckConstraint(
            "(kind = 'product' AND product_id IS NOT NULL AND job_id IS NULL) OR "
            "(kind = 'job' AND job_id IS NOT NULL AND product_id IS NULL) OR "
            "(kind = 'manual' AND product_id IS NULL AND job_id IS NULL)",
            name="ck_sale_item_kind_ref",
        ),
    )

    op.create_index("ix_sale_item_sale_id", "sale_item", ["sale_id"])
    op.create_index("ix_sale_item_product_id", "sale_item", ["product_id"])
    op.create_index("ix_sale_item_job_id", "sale_item", ["job_id"])


def downgrade() -> None:
    op.drop_index("ix_sale_item_job_id", table_name="sale_item")
    op.drop_index("ix_sale_item_product_id", table_name="sale_item")
    op.drop_index("ix_sale_item_sale_id", table_name="sale_item")
    op.drop_table("sale_item")

    op.drop_index("ix_sale_created_at_id", table_name="sale")
    op.drop_index("ix_sale_occurred_at", table_name="sale")
    op.drop_index("ix_sale_channel_id", table_name="sale")
    op.drop_index("ix_sale_state", table_name="sale")
    op.drop_table("sale")

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        sa.Enum(*SALE_ITEM_KIND_VALUES, name="sale_item_kind").drop(bind, checkfirst=True)
        sa.Enum(*SALE_STATE_VALUES, name="sale_state").drop(bind, checkfirst=True)
