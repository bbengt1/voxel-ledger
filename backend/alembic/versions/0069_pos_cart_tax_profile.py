"""Per-cart ``tax_profile_id`` override on ``pos_cart``.

The channel still carries the default tax behavior (POS = collect,
marketplace = none, etc.), but a single sale may need a different
profile — pop-up at a different jurisdiction, wholesale walk-in,
exemption certificate on file. ``NULL`` means "use the channel's
profile."

Revision ID: 0069_pos_cart_tax_profile
Revises: 0068_channel_tax_profile
Create Date: 2026-05-26 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0069_pos_cart_tax_profile"
down_revision: str | None = "0068_channel_tax_profile"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "pos_cart",
        sa.Column(
            "tax_profile_id",
            sa.Uuid(),
            sa.ForeignKey("tax_profile.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("pos_cart", "tax_profile_id")
