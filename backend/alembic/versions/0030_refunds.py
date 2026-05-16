"""refund + refund_item tables (Phase 6.5, #97)

Creates the ``refund`` and ``refund_item`` tables plus the two PG enums
``refund_kind`` and ``refund_state``. Per ops convention (agents.md PG
strict-typing gotcha #1) the enums are NOT pre-created — they're
auto-created by ``op.create_table`` via the columns' dialect hook.

Booleans use ``sa.true()`` / ``sa.false()`` (gotcha "Boolean defaults"),
never ``sa.text("1")``.

Revision ID: 0030_refunds
Revises: 0029_sale_je_fk
Create Date: 2026-05-15 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0030_refunds"
down_revision: str | None = "0029_sale_je_fk"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


REFUND_KIND_VALUES = (
    "full",
    "partial",
    "store_credit",
    "marketplace_initiated",
)

REFUND_STATE_VALUES = (
    "pending_approval",
    "approved",
    "posted",
    "rejected",
    "cancelled",
)


def upgrade() -> None:
    refund_kind_enum = sa.Enum(*REFUND_KIND_VALUES, name="refund_kind")
    refund_state_enum = sa.Enum(*REFUND_STATE_VALUES, name="refund_state")

    op.create_table(
        "refund",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("refund_number", sa.String(length=32), nullable=False, unique=True),
        sa.Column(
            "sale_id",
            sa.Uuid(),
            sa.ForeignKey("sale.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("kind", refund_kind_enum, nullable=False),
        sa.Column(
            "state",
            refund_state_enum,
            nullable=False,
            server_default="pending_approval",
        ),
        sa.Column(
            "total_amount",
            sa.Numeric(18, 6),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "restock_inventory",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column("reason_code", sa.String(length=64), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_by_user_id",
            sa.Uuid(),
            sa.ForeignKey("user.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "approved_by_user_id",
            sa.Uuid(),
            sa.ForeignKey("user.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "approval_request_id",
            sa.Uuid(),
            sa.ForeignKey("approval_request.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "posting_journal_entry_id",
            sa.Uuid(),
            sa.ForeignKey("journal_entry.id", ondelete="SET NULL"),
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
    op.create_index("ix_refund_state", "refund", ["state"])
    op.create_index("ix_refund_sale_id", "refund", ["sale_id"])
    op.create_index("ix_refund_created_at_id", "refund", ["created_at", "id"])
    op.create_index("ix_refund_approval_request_id", "refund", ["approval_request_id"])

    op.create_table(
        "refund_item",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "refund_id",
            sa.Uuid(),
            sa.ForeignKey("refund.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "sale_item_id",
            sa.Uuid(),
            sa.ForeignKey("sale_item.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("quantity", sa.Numeric(18, 6), nullable=False),
        sa.Column("unit_amount", sa.Numeric(18, 6), nullable=False),
        sa.Column("extended_amount", sa.Numeric(18, 6), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("refund_id", "sale_item_id", name="uq_refund_item_refund_sale_item"),
    )
    op.create_index("ix_refund_item_refund_id", "refund_item", ["refund_id"])
    op.create_index("ix_refund_item_sale_item_id", "refund_item", ["sale_item_id"])


def downgrade() -> None:
    op.drop_index("ix_refund_item_sale_item_id", table_name="refund_item")
    op.drop_index("ix_refund_item_refund_id", table_name="refund_item")
    op.drop_table("refund_item")

    op.drop_index("ix_refund_approval_request_id", table_name="refund")
    op.drop_index("ix_refund_created_at_id", table_name="refund")
    op.drop_index("ix_refund_sale_id", table_name="refund")
    op.drop_index("ix_refund_state", table_name="refund")
    op.drop_table("refund")

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        sa.Enum(*REFUND_STATE_VALUES, name="refund_state").drop(bind, checkfirst=True)
        sa.Enum(*REFUND_KIND_VALUES, name="refund_kind").drop(bind, checkfirst=True)
