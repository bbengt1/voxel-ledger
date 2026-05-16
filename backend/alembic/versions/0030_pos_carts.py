"""pos_cart + pos_cart_item tables (Phase 6.4, #96)

Creates the server-side cart state for the POS module along with the
``pos_cart_state`` enum.

Per agents.md PG strict-typing gotcha #1, the enum is NOT pre-created.
``op.create_table`` autocreates the PG type via the column's dialect hook;
on SQLite the same ``sa.Enum`` renders as ``VARCHAR + CHECK``.

Revision ID: 0030_pos_carts
Revises: 0029_sale_je_fk
Create Date: 2026-05-15 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0030_pos_carts"
down_revision: str | None = "0029_sale_je_fk"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


POS_CART_STATE_VALUES = (
    "open",
    "checked_out",
    "voided",
)


def upgrade() -> None:
    pos_cart_state_enum = sa.Enum(*POS_CART_STATE_VALUES, name="pos_cart_state")

    op.create_table(
        "pos_cart",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "cashier_user_id",
            sa.Uuid(),
            sa.ForeignKey("user.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "channel_id",
            sa.Uuid(),
            sa.ForeignKey("sales_channel.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "state",
            pos_cart_state_enum,
            nullable=False,
            server_default="open",
        ),
        sa.Column("customer_name", sa.String(length=255), nullable=True),
        sa.Column("customer_email", sa.String(length=255), nullable=True),
        sa.Column(
            "discount_amount",
            sa.Numeric(18, 6),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "discount_kind",
            sa.String(length=16),
            nullable=True,
        ),
        sa.Column(
            "sale_id",
            sa.Uuid(),
            sa.ForeignKey("sale.id", ondelete="SET NULL"),
            nullable=True,
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
    op.create_index("ix_pos_cart_state", "pos_cart", ["state"])
    op.create_index("ix_pos_cart_cashier_user_id", "pos_cart", ["cashier_user_id"])
    op.create_index("ix_pos_cart_channel_id", "pos_cart", ["channel_id"])

    op.create_table(
        "pos_cart_item",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "cart_id",
            sa.Uuid(),
            sa.ForeignKey("pos_cart.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("line_number", sa.Integer(), nullable=False),
        sa.Column(
            "product_id",
            sa.Uuid(),
            sa.ForeignKey("product.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("sku", sa.String(length=64), nullable=True),
        sa.Column(
            "quantity",
            sa.Numeric(18, 6),
            nullable=False,
            server_default=sa.text("1"),
        ),
        sa.Column("unit_price", sa.Numeric(18, 6), nullable=False),
        sa.Column(
            "discount_amount",
            sa.Numeric(18, 6),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "discount_kind",
            sa.String(length=16),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("cart_id", "line_number", name="uq_pos_cart_item_cart_line"),
    )
    op.create_index("ix_pos_cart_item_cart_id", "pos_cart_item", ["cart_id"])
    op.create_index("ix_pos_cart_item_product_id", "pos_cart_item", ["product_id"])


def downgrade() -> None:
    op.drop_index("ix_pos_cart_item_product_id", table_name="pos_cart_item")
    op.drop_index("ix_pos_cart_item_cart_id", table_name="pos_cart_item")
    op.drop_table("pos_cart_item")

    op.drop_index("ix_pos_cart_channel_id", table_name="pos_cart")
    op.drop_index("ix_pos_cart_cashier_user_id", table_name="pos_cart")
    op.drop_index("ix_pos_cart_state", table_name="pos_cart")
    op.drop_table("pos_cart")

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        sa.Enum(*POS_CART_STATE_VALUES, name="pos_cart_state").drop(bind, checkfirst=True)
