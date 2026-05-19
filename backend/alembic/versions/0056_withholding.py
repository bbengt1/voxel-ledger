"""withholding_profile + vendor / bill_payment_application columns (Phase 9.7, #159).

Adds the structured withholding-profile aggregate (1099-NEC and
foreign-jurisdiction equivalents) plus the per-application stamps that
record how much was withheld and which profile drove the split.

Per agents.md gotcha #1 no enums are added here.

Revision ID: 0056_withholding
Revises: 0055_tax_remittances
Create Date: 2026-05-19 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0056_withholding"
down_revision: str | None = "0055_tax_remittances"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "withholding_profile",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("code", sa.String(length=64), nullable=False, unique=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("jurisdiction", sa.String(length=64), nullable=False),
        sa.Column("rate", sa.Numeric(7, 5), nullable=False),
        sa.Column(
            "liability_account_id",
            sa.Uuid(),
            sa.ForeignKey("account.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("threshold_per_year", sa.Numeric(18, 6), nullable=True),
        sa.Column("form_kind", sa.String(length=32), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column(
            "created_by_user_id",
            sa.Uuid(),
            sa.ForeignKey("user.id", ondelete="RESTRICT"),
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
        sa.CheckConstraint("rate >= 0 AND rate <= 1", name="ck_withholding_profile_rate_range"),
    )
    op.create_index("ix_withholding_profile_is_active", "withholding_profile", ["is_active"])
    op.create_index("ix_withholding_profile_jurisdiction", "withholding_profile", ["jurisdiction"])

    bind = op.get_bind()

    # vendor.withholding_profile_id
    op.add_column(
        "vendor",
        sa.Column("withholding_profile_id", sa.Uuid(), nullable=True),
    )
    if bind.dialect.name != "sqlite":
        op.create_foreign_key(
            "fk_vendor_withholding_profile_id",
            "vendor",
            "withholding_profile",
            ["withholding_profile_id"],
            ["id"],
            ondelete="SET NULL",
        )

    # bill_payment_application: withholding stamps
    op.add_column(
        "bill_payment_application",
        sa.Column(
            "withholding_amount",
            sa.Numeric(18, 6),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.add_column(
        "bill_payment_application",
        sa.Column("withholding_profile_id", sa.Uuid(), nullable=True),
    )
    if bind.dialect.name != "sqlite":
        op.create_foreign_key(
            "fk_bill_payment_application_withholding_profile_id",
            "bill_payment_application",
            "withholding_profile",
            ["withholding_profile_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    bind = op.get_bind()

    if bind.dialect.name != "sqlite":
        op.drop_constraint(
            "fk_bill_payment_application_withholding_profile_id",
            "bill_payment_application",
            type_="foreignkey",
        )
    op.drop_column("bill_payment_application", "withholding_profile_id")
    op.drop_column("bill_payment_application", "withholding_amount")

    if bind.dialect.name != "sqlite":
        op.drop_constraint("fk_vendor_withholding_profile_id", "vendor", type_="foreignkey")
    op.drop_column("vendor", "withholding_profile_id")

    op.drop_index("ix_withholding_profile_jurisdiction", table_name="withholding_profile")
    op.drop_index("ix_withholding_profile_is_active", table_name="withholding_profile")
    op.drop_table("withholding_profile")
