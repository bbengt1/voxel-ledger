"""Add ``sales_channel.default_clearing_account_id`` (Phase 9.9, #161).

The settlement payout JE Cr's the channel's clearing / marketplace-AR
account. Phase 6.1 added ``default_revenue_account_id`` and
``default_fee_account_id`` but missed the clearing leg. This column is
nullable so existing channels migrate cleanly; the settlement post
flow raises if it's unset at the time of posting.

Revision ID: 0057_sales_channel_clearing_account
Revises: 0056_withholding
Create Date: 2026-05-19 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0057_sales_channel_clearing_account"
down_revision: str | None = "0056_withholding"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    op.add_column(
        "sales_channel",
        sa.Column("default_clearing_account_id", sa.Uuid(), nullable=True),
    )
    if bind.dialect.name != "sqlite":
        op.create_foreign_key(
            "fk_sales_channel_default_clearing_account_id",
            "sales_channel",
            "account",
            ["default_clearing_account_id"],
            ["id"],
            ondelete="RESTRICT",
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        op.drop_constraint(
            "fk_sales_channel_default_clearing_account_id",
            "sales_channel",
            type_="foreignkey",
        )
    op.drop_column("sales_channel", "default_clearing_account_id")
