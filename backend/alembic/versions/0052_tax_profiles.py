"""tax_profile + tax_rate tables + per-line tax columns (Phase 9.5, #157)

Adds the structured tax-profile aggregate (replaces the flat
``tax_amount`` flow on invoices/bills with compound + reverse-charge
tax rates that post per-jurisdiction liability credits at issue time).

Per agents.md gotcha #1, no enums are added here (we used booleans for
``is_reverse_charge`` and ``compound_on_previous``).

Sibling heads
-------------
Phase 9.2 landed first at 0051; this rebases onto it.
That's expected: both 0051 (9.2) and 0052 (9.5) branch off 0050. A
follow-up merge migration (or a rebase of whichever lands second) will
collapse them. DO NOT merge heads in this PR.

Revision ID: 0052_tax_profiles
Revises: 0050_fixed_assets
Create Date: 2026-05-18 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0052_tax_profiles"
down_revision: str | None = "0051_depreciation_schedule"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tax_profile",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("code", sa.String(length=64), nullable=False, unique=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("jurisdiction", sa.String(length=64), nullable=False),
        sa.Column(
            "is_reverse_charge",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
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
    )
    op.create_index("ix_tax_profile_is_active", "tax_profile", ["is_active"])
    op.create_index("ix_tax_profile_jurisdiction", "tax_profile", ["jurisdiction"])

    op.create_table(
        "tax_rate",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "profile_id",
            sa.Uuid(),
            sa.ForeignKey("tax_profile.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("rate", sa.Numeric(7, 5), nullable=False),
        sa.Column(
            "liability_account_id",
            sa.Uuid(),
            sa.ForeignKey("account.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "compound_on_previous",
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
        sa.UniqueConstraint("profile_id", "ordinal", name="uq_tax_rate_profile_ordinal"),
    )
    op.create_index("ix_tax_rate_profile_id", "tax_rate", ["profile_id"])

    # --- customer.tax_profile_id : add the FK only (column already exists) ---
    # SQLite doesn't support ALTER TABLE ADD CONSTRAINT for FKs; the column
    # was created without one by Phase 7.1. On PG we can add it; on SQLite
    # we leave the column untouched (tests use SQLite and the column is
    # functionally usable via the ORM relationship).
    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        op.create_foreign_key(
            "fk_customer_tax_profile_id",
            "customer",
            "tax_profile",
            ["tax_profile_id"],
            ["id"],
            ondelete="SET NULL",
        )

    # --- vendor.tax_profile_id : add column + FK ---
    op.add_column(
        "vendor",
        sa.Column("tax_profile_id", sa.Uuid(), nullable=True),
    )
    if bind.dialect.name != "sqlite":
        op.create_foreign_key(
            "fk_vendor_tax_profile_id",
            "vendor",
            "tax_profile",
            ["tax_profile_id"],
            ["id"],
            ondelete="SET NULL",
        )

    # --- invoice_item: tax_profile_id (nullable FK) + tax_amount ---
    op.add_column(
        "invoice_item",
        sa.Column("tax_profile_id", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "invoice_item",
        sa.Column(
            "tax_amount",
            sa.Numeric(18, 6),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    if bind.dialect.name != "sqlite":
        op.create_foreign_key(
            "fk_invoice_item_tax_profile_id",
            "invoice_item",
            "tax_profile",
            ["tax_profile_id"],
            ["id"],
            ondelete="SET NULL",
        )

    # --- bill_item: tax_profile_id + tax_amount ---
    op.add_column(
        "bill_item",
        sa.Column("tax_profile_id", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "bill_item",
        sa.Column(
            "tax_amount",
            sa.Numeric(18, 6),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    if bind.dialect.name != "sqlite":
        op.create_foreign_key(
            "fk_bill_item_tax_profile_id",
            "bill_item",
            "tax_profile",
            ["tax_profile_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    bind = op.get_bind()

    if bind.dialect.name != "sqlite":
        op.drop_constraint("fk_bill_item_tax_profile_id", "bill_item", type_="foreignkey")
    op.drop_column("bill_item", "tax_amount")
    op.drop_column("bill_item", "tax_profile_id")

    if bind.dialect.name != "sqlite":
        op.drop_constraint("fk_invoice_item_tax_profile_id", "invoice_item", type_="foreignkey")
    op.drop_column("invoice_item", "tax_amount")
    op.drop_column("invoice_item", "tax_profile_id")

    if bind.dialect.name != "sqlite":
        op.drop_constraint("fk_vendor_tax_profile_id", "vendor", type_="foreignkey")
    op.drop_column("vendor", "tax_profile_id")

    if bind.dialect.name != "sqlite":
        op.drop_constraint("fk_customer_tax_profile_id", "customer", type_="foreignkey")

    op.drop_index("ix_tax_rate_profile_id", table_name="tax_rate")
    op.drop_table("tax_rate")
    op.drop_index("ix_tax_profile_jurisdiction", table_name="tax_profile")
    op.drop_index("ix_tax_profile_is_active", table_name="tax_profile")
    op.drop_table("tax_profile")
