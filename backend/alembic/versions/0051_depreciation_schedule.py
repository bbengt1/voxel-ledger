"""depreciation_schedule_entry table + depreciation_entry_state enum (Phase 9.2, #154)

Stores the up-front month-by-month plan for each fixed-asset's
depreciation. Phase 9.3's worker walks the planned rows and posts JEs,
flipping ``state`` from ``planned`` to ``posted``.

Per agents.md gotcha #1 the ``depreciation_entry_state`` enum is NOT
pre-created — ``op.create_table`` auto-creates it via the column dialect
hook. On SQLite the same ``sa.Enum`` renders as ``VARCHAR + CHECK``.

The ``journal_entry_id`` FK uses ``ondelete='SET NULL'`` so that if a JE
is deleted (e.g. a Phase 9.4 disposal reverses + deletes), the schedule
row survives marking that period as unposted.

Revision ID: 0051_depreciation_schedule
Revises: 0050_fixed_assets
Create Date: 2026-05-18 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0051_depreciation_schedule"
down_revision: str | None = "0050_fixed_assets"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


DEPRECIATION_ENTRY_STATE_VALUES = ("planned", "posted", "adjusted")


def upgrade() -> None:
    depreciation_entry_state = sa.Enum(
        *DEPRECIATION_ENTRY_STATE_VALUES, name="depreciation_entry_state"
    )

    op.create_table(
        "depreciation_schedule_entry",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "asset_id",
            sa.Uuid(),
            sa.ForeignKey("fixed_asset.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("period_index", sa.Integer(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("opening_book_value", sa.Numeric(18, 6), nullable=False),
        sa.Column("depreciation_amount", sa.Numeric(18, 6), nullable=False),
        sa.Column("closing_book_value", sa.Numeric(18, 6), nullable=False),
        sa.Column(
            "state",
            depreciation_entry_state,
            nullable=False,
            server_default="planned",
        ),
        sa.Column(
            "journal_entry_id",
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
        sa.UniqueConstraint("asset_id", "period_index", name="uq_depreciation_entry_asset_period"),
    )

    op.create_index(
        "ix_depreciation_entry_asset_period_end",
        "depreciation_schedule_entry",
        ["asset_id", "period_end"],
    )
    op.create_index(
        "ix_depreciation_entry_state_period_end",
        "depreciation_schedule_entry",
        ["state", "period_end"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_depreciation_entry_state_period_end",
        table_name="depreciation_schedule_entry",
    )
    op.drop_index(
        "ix_depreciation_entry_asset_period_end",
        table_name="depreciation_schedule_entry",
    )
    op.drop_table("depreciation_schedule_entry")

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        sa.Enum(*DEPRECIATION_ENTRY_STATE_VALUES, name="depreciation_entry_state").drop(
            bind, checkfirst=True
        )
