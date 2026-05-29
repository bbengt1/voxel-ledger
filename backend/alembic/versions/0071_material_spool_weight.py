"""Add ``spool_weight_grams`` to ``material``.

Spool-centric inventory entry model: every material has a per-spool
weight, and receipts are recorded as
``(spools * spool_weight_grams) + extra_grams`` at a price-per-spool.
The DB column defaults to ``0`` purely so this migration runs cleanly
against the existing production rows; the API layer rejects ``0`` on
new materials and on receipts. Existing rows must be backfilled via
the UI before they can accept new receipts.

Revision ID: 0071_material_spool_weight
Revises: 0070_supply_pieces_per_unit
Create Date: 2026-05-28 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0071_material_spool_weight"
down_revision: str | None = "0070_supply_pieces_per_unit"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "material",
        sa.Column(
            "spool_weight_grams",
            sa.Numeric(18, 6),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.create_check_constraint(
        "ck_material_spool_weight_grams_non_negative",
        "material",
        "spool_weight_grams >= 0",
    )


def downgrade() -> None:
    op.drop_constraint("ck_material_spool_weight_grams_non_negative", "material", type_="check")
    op.drop_column("material", "spool_weight_grams")
