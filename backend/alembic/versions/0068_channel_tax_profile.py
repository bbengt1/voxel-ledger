"""Per-channel tax profile FK on ``sales_channel``.

POS, marketplace, direct-web, and wholesale channels each pick a tax
behavior independently. The optional ``tax_profile_id`` lets a channel
reuse the existing :class:`TaxProfile` machinery (multi-rate, compound
rates, per-rate liability accounts, remittance flow). ``NULL`` means
the channel doesn't compute tax — the caller supplies a flat amount or
zero, matching the previous behavior.

Revision ID: 0068_channel_tax_profile
Revises: 0067_printer_status
Create Date: 2026-05-26 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0068_channel_tax_profile"
down_revision: str | None = "0067_printer_status"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "sales_channel",
        sa.Column(
            "tax_profile_id",
            sa.Uuid(),
            sa.ForeignKey("tax_profile.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_sales_channel_tax_profile",
        "sales_channel",
        ["tax_profile_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_sales_channel_tax_profile", table_name="sales_channel")
    op.drop_column("sales_channel", "tax_profile_id")
