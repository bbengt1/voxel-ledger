"""Add ``pieces_per_unit`` to ``supply``.

Operator-supplied count of individual pieces inside each purchase unit
(e.g. ``unit = "box"``, ``pieces_per_unit = 100`` for a box of 100
screws). Nullable so existing rows stay valid; when present, the UI
shows the breakdown alongside on-hand totals.

Revision ID: 0070_supply_pieces_per_unit
Revises: 0069_pos_cart_tax_profile
Create Date: 2026-05-27 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0070_supply_pieces_per_unit"
down_revision: str | None = "0069_pos_cart_tax_profile"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "supply",
        sa.Column("pieces_per_unit", sa.Integer(), nullable=True),
    )
    # Enforce positive piece counts at the DB layer.
    op.create_check_constraint(
        "ck_supply_pieces_per_unit_positive",
        "supply",
        "pieces_per_unit IS NULL OR pieces_per_unit >= 1",
    )


def downgrade() -> None:
    op.drop_constraint("ck_supply_pieces_per_unit_positive", "supply", type_="check")
    op.drop_column("supply", "pieces_per_unit")
