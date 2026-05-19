"""fixed_asset_disposal table + asset_disposal_kind enum (Phase 9.4, #156).

Operator disposes of a fixed asset (sale / scrap / writeoff / donation).
The service posts a balanced JE in the same TX that clears accumulated
depreciation + asset cost against proceeds and a gain/loss line.

Sibling head note
-----------------
Phase 9.6 (#158) also targets ``0054`` on top of ``0053_settlements``;
whichever PR lands first owns the linear history and the loser will
rebase. Both are pure additive changes so the rebase is mechanical.

Per agents.md gotcha #1 the new ``asset_disposal_kind`` enum is NOT
pre-created — ``op.create_table`` auto-creates it via the column
dialect hook.

Revision ID: 0054_asset_disposal
Revises: 0053_settlements
Create Date: 2026-05-19 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0054_asset_disposal"
down_revision: str | None = "0053_settlements"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


ASSET_DISPOSAL_KIND_VALUES = ("sale", "scrap", "writeoff", "donation")


def upgrade() -> None:
    kind_enum = sa.Enum(*ASSET_DISPOSAL_KIND_VALUES, name="asset_disposal_kind")

    op.create_table(
        "fixed_asset_disposal",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "asset_id",
            sa.Uuid(),
            sa.ForeignKey("fixed_asset.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("disposed_on", sa.Date(), nullable=False),
        sa.Column("disposal_kind", kind_enum, nullable=False),
        sa.Column(
            "proceeds_amount",
            sa.Numeric(18, 6),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "proceeds_account_id",
            sa.Uuid(),
            sa.ForeignKey("account.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "gain_loss_account_id",
            sa.Uuid(),
            sa.ForeignKey("account.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("book_value_at_disposal", sa.Numeric(18, 6), nullable=False),
        sa.Column("accumulated_depreciation_at_disposal", sa.Numeric(18, 6), nullable=False),
        sa.Column("gain_loss_amount", sa.Numeric(18, 6), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "posting_journal_entry_id",
            sa.Uuid(),
            sa.ForeignKey("journal_entry.id", ondelete="SET NULL"),
            nullable=True,
        ),
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
        sa.CheckConstraint("proceeds_amount >= 0", name="ck_fixed_asset_disposal_proceeds_nonneg"),
        sa.UniqueConstraint("asset_id", name="uq_fixed_asset_disposal_asset"),
    )

    op.create_index("ix_fixed_asset_disposal_asset_id", "fixed_asset_disposal", ["asset_id"])
    op.create_index("ix_fixed_asset_disposal_disposed_on", "fixed_asset_disposal", ["disposed_on"])


def downgrade() -> None:
    op.drop_index("ix_fixed_asset_disposal_disposed_on", table_name="fixed_asset_disposal")
    op.drop_index("ix_fixed_asset_disposal_asset_id", table_name="fixed_asset_disposal")
    op.drop_table("fixed_asset_disposal")

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("DROP TYPE IF EXISTS asset_disposal_kind")
