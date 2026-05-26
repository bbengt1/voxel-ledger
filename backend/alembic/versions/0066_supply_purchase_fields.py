"""Per-supply ``item_number`` + ``place_of_purchase`` columns.

Operator-supplied SKU/order number (e.g. an Amazon ASIN or Home Depot
SKU) and the storefront the supply is reordered from. Both optional —
existing rows stay valid.

Revision ID: 0066_supply_purchase_fields
Revises: 0065_printer_cost_fields
Create Date: 2026-05-26 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0066_supply_purchase_fields"
down_revision: str | None = "0065_printer_cost_fields"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "supply",
        sa.Column("item_number", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "supply",
        sa.Column("place_of_purchase", sa.String(length=128), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("supply", "place_of_purchase")
    op.drop_column("supply", "item_number")
