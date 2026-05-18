"""settlement + settlement_line tables (Phase 9.8, #160).

Marketplace settlement imports. Operators upload a marketplace payout
CSV (Etsy / Amazon / Shopify / generic) and we parse it into a
``settlement`` row + N ``settlement_line`` child rows. The settlement
flows ``imported -> matched -> posted`` and can be cancelled before
posting (Phase 9.9 owns the post + reversal flow).

Per agents.md gotcha #1 the three new enums (``settlement_state``,
``settlement_line_kind``, ``settlement_line_state``) are NOT pre-created
— ``op.create_table`` auto-creates the PG types via the column dialect
hook. On SQLite the same ``sa.Enum`` renders as ``VARCHAR + CHECK``.

NOTE: Phase 9.2 and 9.5 are sibling heads off ``0050_fixed_assets`` —
whichever PR merges first defines the linear history downstream and the
other two will need a head-merge migration. Expected; not a blocker.

Revision ID: 0053_settlements
Revises: 0050_fixed_assets
Create Date: 2026-05-18 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0053_settlements"
down_revision: str | None = "0052_tax_profiles"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


SETTLEMENT_STATE_VALUES = ("imported", "matched", "posted", "cancelled")
SETTLEMENT_LINE_KIND_VALUES = ("sale", "refund", "fee", "adjustment", "payout", "tax")
SETTLEMENT_LINE_STATE_VALUES = ("unmatched", "matched", "ignored")


def upgrade() -> None:
    settlement_state = sa.Enum(*SETTLEMENT_STATE_VALUES, name="settlement_state")
    settlement_line_kind = sa.Enum(*SETTLEMENT_LINE_KIND_VALUES, name="settlement_line_kind")
    settlement_line_state = sa.Enum(*SETTLEMENT_LINE_STATE_VALUES, name="settlement_line_state")

    op.create_table(
        "settlement",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("settlement_number", sa.String(length=32), nullable=False, unique=True),
        sa.Column(
            "channel_id",
            sa.Uuid(),
            sa.ForeignKey("sales_channel.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("gross_amount", sa.Numeric(18, 6), nullable=False),
        sa.Column("fee_amount", sa.Numeric(18, 6), nullable=False),
        sa.Column("refund_amount", sa.Numeric(18, 6), nullable=False),
        sa.Column(
            "adjustment_amount",
            sa.Numeric(18, 6),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("payout_amount", sa.Numeric(18, 6), nullable=False),
        sa.Column(
            "payout_account_id",
            sa.Uuid(),
            sa.ForeignKey("account.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column(
            "imported_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "imported_by_user_id",
            sa.Uuid(),
            sa.ForeignKey("user.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "state",
            settlement_state,
            nullable=False,
            server_default="imported",
        ),
        sa.Column(
            "posting_journal_entry_id",
            sa.Uuid(),
            sa.ForeignKey("journal_entry.id", ondelete="SET NULL"),
            nullable=True,
        ),
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
    )

    op.create_index(
        "ix_settlement_channel_period_end",
        "settlement",
        ["channel_id", sa.text("period_end DESC")],
    )
    op.create_index("ix_settlement_state", "settlement", ["state"])
    op.create_index("ix_settlement_imported_at", "settlement", [sa.text("imported_at DESC")])

    op.create_table(
        "settlement_line",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "settlement_id",
            sa.Uuid(),
            sa.ForeignKey("settlement.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("line_number", sa.Integer(), nullable=False),
        sa.Column("line_kind", settlement_line_kind, nullable=False),
        sa.Column("occurred_on", sa.Date(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("external_order_id", sa.String(length=128), nullable=True),
        sa.Column("external_txn_id", sa.String(length=128), nullable=True),
        sa.Column("amount", sa.Numeric(18, 6), nullable=False),
        sa.Column(
            "state",
            settlement_line_state,
            nullable=False,
            server_default="unmatched",
        ),
        sa.Column(
            "matched_sale_id",
            sa.Uuid(),
            sa.ForeignKey("sale.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "matched_refund_id",
            sa.Uuid(),
            sa.ForeignKey("refund.id", ondelete="SET NULL"),
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

    # Partial unique on (settlement_id, external_txn_id) where the
    # external_txn_id is non-null. Dedup across re-imports of the same file.
    op.create_index(
        "ux_settlement_line_external_txn",
        "settlement_line",
        ["settlement_id", "external_txn_id"],
        unique=True,
        sqlite_where=sa.text("external_txn_id IS NOT NULL"),
        postgresql_where=sa.text("external_txn_id IS NOT NULL"),
    )
    op.create_index(
        "ix_settlement_line_settlement_line_number",
        "settlement_line",
        ["settlement_id", "line_number"],
    )
    op.create_index(
        "ix_settlement_line_settlement_state",
        "settlement_line",
        ["settlement_id", "state"],
    )
    op.create_index(
        "ix_settlement_line_external_order_id",
        "settlement_line",
        ["external_order_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_settlement_line_external_order_id", table_name="settlement_line")
    op.drop_index("ix_settlement_line_settlement_state", table_name="settlement_line")
    op.drop_index("ix_settlement_line_settlement_line_number", table_name="settlement_line")
    op.drop_index("ux_settlement_line_external_txn", table_name="settlement_line")
    op.drop_table("settlement_line")

    op.drop_index("ix_settlement_imported_at", table_name="settlement")
    op.drop_index("ix_settlement_state", table_name="settlement")
    op.drop_index("ix_settlement_channel_period_end", table_name="settlement")
    op.drop_table("settlement")

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        sa.Enum(*SETTLEMENT_LINE_STATE_VALUES, name="settlement_line_state").drop(
            bind, checkfirst=True
        )
        sa.Enum(*SETTLEMENT_LINE_KIND_VALUES, name="settlement_line_kind").drop(
            bind, checkfirst=True
        )
        sa.Enum(*SETTLEMENT_STATE_VALUES, name="settlement_state").drop(bind, checkfirst=True)
