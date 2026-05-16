"""shipment table + shipment_state enum (Phase 6.6, #98)

Creates the ``shipment`` table — one row per shipment created for a sale,
plus the ``shipment_state`` PG enum. Per agents.md PG strict-typing
gotcha #1 the enum is NOT pre-created — ``op.create_table`` auto-creates
it via the column's dialect hook.

Revision ID: 0030_shipments
Revises: 0029_sale_je_fk
Create Date: 2026-05-15 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0030_shipments"
down_revision: str | None = "0029_sale_je_fk"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


SHIPMENT_STATE_VALUES = (
    "pending",
    "label_purchased",
    "shipped",
    "delivered",
    "returned",
    "cancelled",
)


def upgrade() -> None:
    shipment_state_enum = sa.Enum(*SHIPMENT_STATE_VALUES, name="shipment_state")

    op.create_table(
        "shipment",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "sale_id",
            sa.Uuid(),
            sa.ForeignKey("sale.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "state",
            shipment_state_enum,
            nullable=False,
            server_default="pending",
        ),
        sa.Column("carrier", sa.Text(), nullable=False),
        sa.Column("service_level", sa.Text(), nullable=True),
        sa.Column("tracking_number", sa.Text(), nullable=True),
        sa.Column("tracking_url", sa.Text(), nullable=True),
        sa.Column("label_pdf_storage_key", sa.Text(), nullable=True),
        sa.Column(
            "cost_amount",
            sa.Numeric(18, 6),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("weight_grams", sa.Integer(), nullable=True),
        sa.Column("dimensions_cm", sa.JSON(), nullable=True),
        sa.Column("ship_from", sa.JSON(), nullable=False),
        sa.Column("ship_to", sa.JSON(), nullable=False),
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
    op.create_index("ix_shipment_sale_id", "shipment", ["sale_id"])
    op.create_index("ix_shipment_state", "shipment", ["state"])
    op.create_index("ix_shipment_tracking_number", "shipment", ["tracking_number"])


def downgrade() -> None:
    op.drop_index("ix_shipment_tracking_number", table_name="shipment")
    op.drop_index("ix_shipment_state", table_name="shipment")
    op.drop_index("ix_shipment_sale_id", table_name="shipment")
    op.drop_table("shipment")

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        sa.Enum(*SHIPMENT_STATE_VALUES, name="shipment_state").drop(bind, checkfirst=True)
