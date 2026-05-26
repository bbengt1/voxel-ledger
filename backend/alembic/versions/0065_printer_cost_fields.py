"""Per-printer cost fields for Snapmaker U1 pricing (#249).

Adds optional depreciation and preheat inputs to ``printer`` so the cost
engine can compute electricity + preheat + per-hour depreciation
in place of (or alongside) the flat ``machine_rate_per_hour`` setting.

Every column is nullable — printers without these fields keep using the
existing flat ``machine_rate_per_hour`` path. When a printer has the
full set (purchase_price, salvage_value, lifespan_years,
annual_print_hours, plus power_draw_watts already on the row), the
cost engine derives a per-hour cost from those inputs.

Revision ID: 0065_printer_cost_fields
Revises: 0064_deposit_slip
Create Date: 2026-05-26 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0065_printer_cost_fields"
down_revision: str | None = "0064_deposit_slip"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "printer",
        sa.Column("purchase_price", sa.Numeric(18, 6), nullable=True),
    )
    op.add_column(
        "printer",
        sa.Column("salvage_value", sa.Numeric(18, 6), nullable=True),
    )
    op.add_column(
        "printer",
        sa.Column("lifespan_years", sa.Integer(), nullable=True),
    )
    op.add_column(
        "printer",
        sa.Column("annual_print_hours", sa.Integer(), nullable=True),
    )
    op.add_column(
        "printer",
        sa.Column("preheat_minutes", sa.Integer(), nullable=True),
    )
    op.add_column(
        "printer",
        sa.Column("preheat_power_watts", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("printer", "preheat_power_watts")
    op.drop_column("printer", "preheat_minutes")
    op.drop_column("printer", "annual_print_hours")
    op.drop_column("printer", "lifespan_years")
    op.drop_column("printer", "salvage_value")
    op.drop_column("printer", "purchase_price")
