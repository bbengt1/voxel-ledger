"""vendor + vendor_contact tables + vendor_state enum (Phase 8.1, #128)

Creates the ``vendor`` and ``vendor_contact`` tables for the AP
aggregate. Mirrors Phase 7.1's ``customer`` tables on the AR side; Phase
8.2 will land ``bill`` rows that reference ``vendor.id``.

Per agents.md gotcha #1 the ``vendor_state`` enum is NOT pre-created —
``op.create_table`` auto-creates it via the column's dialect hook.
Boolean defaults use ``sa.false()`` per the booleans gotcha.

Revision ID: 0040_vendors
Revises: 0038_late_fees
Create Date: 2026-05-16 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0040_vendors"
down_revision: str | None = "0038_late_fees"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


VENDOR_STATE_VALUES = ("active", "archived")


def upgrade() -> None:
    vendor_state_enum = sa.Enum(*VENDOR_STATE_VALUES, name="vendor_state")

    op.create_table(
        "vendor",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("vendor_number", sa.String(32), nullable=False, unique=True),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("legal_name", sa.String(255), nullable=True),
        sa.Column("primary_email", sa.String(255), nullable=True),
        sa.Column("phone", sa.String(64), nullable=True),
        sa.Column("billing_address", sa.JSON(), nullable=True),
        sa.Column("shipping_address", sa.JSON(), nullable=True),
        sa.Column(
            "payment_terms_days",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("30"),
        ),
        sa.Column(
            "default_expense_account_id",
            sa.Uuid(),
            sa.ForeignKey("account.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "default_ap_account_id",
            sa.Uuid(),
            sa.ForeignKey("account.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("tax_id", sa.String(64), nullable=True),
        sa.Column(
            "is_1099_vendor",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "state",
            vendor_state_enum,
            nullable=False,
            server_default="active",
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
    )
    op.create_index("ix_vendor_state", "vendor", ["state"])
    op.create_index("ix_vendor_display_name", "vendor", ["display_name"])

    op.create_table(
        "vendor_contact",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "vendor_id",
            sa.Uuid(),
            sa.ForeignKey("vendor.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("phone", sa.String(64), nullable=True),
        sa.Column("role_label", sa.Text(), nullable=True),
        sa.Column(
            "is_primary",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
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
    )
    op.create_index("ix_vendor_contact_vendor_id", "vendor_contact", ["vendor_id"])


def downgrade() -> None:
    op.drop_index("ix_vendor_contact_vendor_id", table_name="vendor_contact")
    op.drop_table("vendor_contact")
    op.drop_index("ix_vendor_display_name", table_name="vendor")
    op.drop_index("ix_vendor_state", table_name="vendor")
    op.drop_table("vendor")

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        sa.Enum(*VENDOR_STATE_VALUES, name="vendor_state").drop(bind, checkfirst=True)
