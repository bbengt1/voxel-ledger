"""tax_remittance table (Phase 9.6, #158).

Operator records remittance payments to revenue authorities against a
tax profile. The service posts a balanced JE (Dr per-rate liability /
Cr bank) in the same transaction.

Per agents.md gotcha #1 the two new enums (``tax_remittance_state``,
``tax_remittance_method``) are NOT pre-created; ``op.create_table``
auto-creates the PG types via the column dialect hook.

Revision ID: 0055_tax_remittances
Revises: 0054_asset_disposal
Create Date: 2026-05-19 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0055_tax_remittances"
down_revision: str | None = "0054_asset_disposal"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


TAX_REMITTANCE_STATE_VALUES = ("recorded", "cancelled")
TAX_REMITTANCE_METHOD_VALUES = ("ach", "check", "wire", "other")


def upgrade() -> None:
    state_enum = sa.Enum(*TAX_REMITTANCE_STATE_VALUES, name="tax_remittance_state")
    method_enum = sa.Enum(*TAX_REMITTANCE_METHOD_VALUES, name="tax_remittance_method")

    op.create_table(
        "tax_remittance",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("remittance_number", sa.String(length=32), nullable=False, unique=True),
        sa.Column(
            "profile_id",
            sa.Uuid(),
            sa.ForeignKey("tax_profile.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("amount_paid", sa.Numeric(18, 6), nullable=False),
        sa.Column("paid_on", sa.Date(), nullable=False),
        sa.Column("method", method_enum, nullable=False),
        sa.Column("reference_number", sa.String(length=64), nullable=True),
        sa.Column(
            "bank_account_id",
            sa.Uuid(),
            sa.ForeignKey("account.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "state",
            state_enum,
            nullable=False,
            server_default="recorded",
        ),
        sa.Column(
            "posting_journal_entry_id",
            sa.Uuid(),
            sa.ForeignKey("journal_entry.id", ondelete="SET NULL"),
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
        sa.CheckConstraint("amount_paid > 0", name="ck_tax_remittance_amount_positive"),
        sa.CheckConstraint("period_end >= period_start", name="ck_tax_remittance_period_range"),
    )
    op.create_index("ix_tax_remittance_profile_id", "tax_remittance", ["profile_id"])
    op.create_index("ix_tax_remittance_state", "tax_remittance", ["state"])
    op.create_index("ix_tax_remittance_paid_on", "tax_remittance", ["paid_on"])


def downgrade() -> None:
    op.drop_index("ix_tax_remittance_paid_on", table_name="tax_remittance")
    op.drop_index("ix_tax_remittance_state", table_name="tax_remittance")
    op.drop_index("ix_tax_remittance_profile_id", table_name="tax_remittance")
    op.drop_table("tax_remittance")

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("DROP TYPE IF EXISTS tax_remittance_state")
        op.execute("DROP TYPE IF EXISTS tax_remittance_method")
