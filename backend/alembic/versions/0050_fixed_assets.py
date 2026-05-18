"""fixed_asset table + 4 new enums (Phase 9.1, #153)

Creates the ``fixed_asset`` aggregate that covers both tangible and
intangible assets (the ``asset_kind`` enum is the discriminator). The
acquisition flow (in ``app.services.fixed_assets``) inserts the row +
posts a JE atomically inside the same DB transaction.

Per agents.md gotcha #1 the four enums (``fixed_asset_kind``,
``fixed_asset_class``, ``depreciation_method``, ``fixed_asset_state``)
are NOT pre-created — ``op.create_table`` auto-creates them via the
columns' dialect hook. On SQLite the same ``sa.Enum`` renders as
``VARCHAR + CHECK``.

Revision ID: 0050_fixed_assets
Revises: 0049_bank_reconciliation
Create Date: 2026-05-18 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0050_fixed_assets"
down_revision: str | None = "0049_bank_reconciliation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


FIXED_ASSET_KIND_VALUES = ("tangible", "intangible")
FIXED_ASSET_CLASS_VALUES = (
    "machine",
    "printer",
    "computer",
    "furniture",
    "vehicle",
    "software",
    "intellectual_property",
    "other",
)
DEPRECIATION_METHOD_VALUES = (
    "straight_line",
    "declining_balance_200",
    "declining_balance_150",
    "none",
)
FIXED_ASSET_STATE_VALUES = ("active", "disposed", "written_off")


def upgrade() -> None:
    fixed_asset_kind = sa.Enum(*FIXED_ASSET_KIND_VALUES, name="fixed_asset_kind")
    fixed_asset_class = sa.Enum(*FIXED_ASSET_CLASS_VALUES, name="fixed_asset_class")
    depreciation_method = sa.Enum(*DEPRECIATION_METHOD_VALUES, name="depreciation_method")
    fixed_asset_state = sa.Enum(*FIXED_ASSET_STATE_VALUES, name="fixed_asset_state")

    op.create_table(
        "fixed_asset",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("asset_number", sa.String(length=32), nullable=False, unique=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("asset_kind", fixed_asset_kind, nullable=False),
        sa.Column("asset_class", fixed_asset_class, nullable=False),
        sa.Column("acquired_on", sa.Date(), nullable=False),
        sa.Column("acquisition_cost", sa.Numeric(18, 6), nullable=False),
        sa.Column(
            "salvage_value",
            sa.Numeric(18, 6),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("useful_life_months", sa.Integer(), nullable=False),
        sa.Column("depreciation_method", depreciation_method, nullable=False),
        sa.Column(
            "asset_account_id",
            sa.Uuid(),
            sa.ForeignKey("account.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "accumulated_depreciation_account_id",
            sa.Uuid(),
            sa.ForeignKey("account.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "depreciation_expense_account_id",
            sa.Uuid(),
            sa.ForeignKey("account.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("serial_number", sa.String(length=128), nullable=True),
        sa.Column(
            "vendor_id",
            sa.Uuid(),
            sa.ForeignKey("vendor.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "acquisition_bill_id",
            sa.Uuid(),
            sa.ForeignKey("bill.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "state",
            fixed_asset_state,
            nullable=False,
            server_default="active",
        ),
        sa.Column("last_depreciated_on", sa.Date(), nullable=True),
        sa.Column(
            "posting_journal_entry_id",
            sa.Uuid(),
            sa.ForeignKey("journal_entry.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("notes", sa.Text(), nullable=True),
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
        sa.CheckConstraint("acquisition_cost > 0", name="ck_fixed_asset_cost_positive"),
        sa.CheckConstraint("salvage_value >= 0", name="ck_fixed_asset_salvage_nonneg"),
        sa.CheckConstraint("useful_life_months > 0", name="ck_fixed_asset_life_positive"),
    )

    op.create_index("ix_fixed_asset_kind", "fixed_asset", ["asset_kind"])
    op.create_index("ix_fixed_asset_class", "fixed_asset", ["asset_class"])
    op.create_index("ix_fixed_asset_state", "fixed_asset", ["state"])
    op.create_index("ix_fixed_asset_vendor_id", "fixed_asset", ["vendor_id"])
    op.create_index("ix_fixed_asset_acquisition_bill_id", "fixed_asset", ["acquisition_bill_id"])
    op.create_index("ix_fixed_asset_created_at_id", "fixed_asset", ["created_at", "id"])


def downgrade() -> None:
    op.drop_index("ix_fixed_asset_created_at_id", table_name="fixed_asset")
    op.drop_index("ix_fixed_asset_acquisition_bill_id", table_name="fixed_asset")
    op.drop_index("ix_fixed_asset_vendor_id", table_name="fixed_asset")
    op.drop_index("ix_fixed_asset_state", table_name="fixed_asset")
    op.drop_index("ix_fixed_asset_class", table_name="fixed_asset")
    op.drop_index("ix_fixed_asset_kind", table_name="fixed_asset")
    op.drop_table("fixed_asset")

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        sa.Enum(*FIXED_ASSET_STATE_VALUES, name="fixed_asset_state").drop(bind, checkfirst=True)
        sa.Enum(*DEPRECIATION_METHOD_VALUES, name="depreciation_method").drop(bind, checkfirst=True)
        sa.Enum(*FIXED_ASSET_CLASS_VALUES, name="fixed_asset_class").drop(bind, checkfirst=True)
        sa.Enum(*FIXED_ASSET_KIND_VALUES, name="fixed_asset_kind").drop(bind, checkfirst=True)
