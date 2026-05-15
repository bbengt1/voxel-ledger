"""sales_channel table (Phase 6.1, #93)

Creates the ``sales_channel`` table plus the ``sales_channel_kind`` and
``sales_channel_fee_model`` PG enums.

Per ops convention (see #49 / agents.md PG strict-typing gotcha #1), the
enums are NOT pre-created. ``op.create_table`` autocreates the PG types
via the columns' dialect hook; on SQLite the same ``sa.Enum`` renders as
``VARCHAR + CHECK``.

Boolean defaults use ``sa.false()`` / ``sa.true()`` per gotcha #4.

Revision ID: 0026_sales_channels
Revises: 0025_production_orders
Create Date: 2026-05-15 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0026_sales_channels"
down_revision: str | None = "0025_production_orders"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


SALES_CHANNEL_KIND_VALUES = (
    "pos",
    "marketplace",
    "direct_web",
    "wholesale",
    "other",
)

SALES_CHANNEL_FEE_MODEL_VALUES = (
    "none",
    "flat",
    "percent",
    "percent_plus_flat",
)


def upgrade() -> None:
    sales_channel_kind_enum = sa.Enum(*SALES_CHANNEL_KIND_VALUES, name="sales_channel_kind")
    sales_channel_fee_model_enum = sa.Enum(
        *SALES_CHANNEL_FEE_MODEL_VALUES, name="sales_channel_fee_model"
    )

    op.create_table(
        "sales_channel",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False, unique=True),
        sa.Column("slug", sa.String(length=64), nullable=False, unique=True),
        sa.Column("kind", sales_channel_kind_enum, nullable=False),
        sa.Column("fee_model", sales_channel_fee_model_enum, nullable=False),
        sa.Column("fee_percent", sa.Numeric(7, 4), nullable=True),
        sa.Column("fee_flat", sa.Numeric(18, 6), nullable=True),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column(
            "default_revenue_account_id",
            sa.Uuid(),
            sa.ForeignKey("account.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "default_fee_account_id",
            sa.Uuid(),
            sa.ForeignKey("account.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("external_id_format_hint", sa.Text(), nullable=True),
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

    op.create_index("ix_sales_channel_is_active", "sales_channel", ["is_active"])
    op.create_index("ix_sales_channel_kind", "sales_channel", ["kind"])


def downgrade() -> None:
    op.drop_index("ix_sales_channel_kind", table_name="sales_channel")
    op.drop_index("ix_sales_channel_is_active", table_name="sales_channel")
    op.drop_table("sales_channel")

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        sa.Enum(*SALES_CHANNEL_FEE_MODEL_VALUES, name="sales_channel_fee_model").drop(
            bind, checkfirst=True
        )
        sa.Enum(*SALES_CHANNEL_KIND_VALUES, name="sales_channel_kind").drop(bind, checkfirst=True)
