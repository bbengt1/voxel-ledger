"""customer + customer_contact tables + customer_state enum (Phase 7.1, #109)

Creates the ``customer`` and ``customer_contact`` tables for the AR
aggregate. Adds nullable ``customer_id`` FK columns to ``sale`` and
``pos_cart`` so Phase 6 rows can opt-in to a real customer reference
without breaking existing POS walk-in snapshots. Per agents.md gotcha #1
the ``customer_state`` enum is NOT pre-created — ``op.create_table``
auto-creates it via the column's dialect hook. Boolean defaults use
``sa.false()`` per the booleans gotcha.

Revision ID: 0033_customers
Revises: 0032_shipments
Create Date: 2026-05-15 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0033_customers"
down_revision: str | None = "0032_shipments"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


CUSTOMER_STATE_VALUES = ("active", "archived")


def upgrade() -> None:
    customer_state_enum = sa.Enum(*CUSTOMER_STATE_VALUES, name="customer_state")

    op.create_table(
        "customer",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("customer_number", sa.String(32), nullable=False, unique=True),
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
            "default_revenue_account_id",
            sa.Uuid(),
            sa.ForeignKey("account.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "default_ar_account_id",
            sa.Uuid(),
            sa.ForeignKey("account.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        # tax_profile_id: Phase 9 will land the tax_profile table; nullable
        # today, no real FK target yet.
        sa.Column("tax_profile_id", sa.Uuid(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "state",
            customer_state_enum,
            nullable=False,
            server_default="active",
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
    op.create_index("ix_customer_state", "customer", ["state"])
    op.create_index("ix_customer_display_name", "customer", ["display_name"])

    op.create_table(
        "customer_contact",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "customer_id",
            sa.Uuid(),
            sa.ForeignKey("customer.id", ondelete="CASCADE"),
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
    op.create_index("ix_customer_contact_customer_id", "customer_contact", ["customer_id"])

    # FK backfill on sale + pos_cart. NULLABLE — legacy rows stay null.
    op.add_column(
        "sale",
        sa.Column(
            "customer_id",
            sa.Uuid(),
            sa.ForeignKey("customer.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_sale_customer_id", "sale", ["customer_id"])

    op.add_column(
        "pos_cart",
        sa.Column(
            "customer_id",
            sa.Uuid(),
            sa.ForeignKey("customer.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("pos_cart", "customer_id")
    op.drop_index("ix_sale_customer_id", table_name="sale")
    op.drop_column("sale", "customer_id")

    op.drop_index("ix_customer_contact_customer_id", table_name="customer_contact")
    op.drop_table("customer_contact")
    op.drop_index("ix_customer_display_name", table_name="customer")
    op.drop_index("ix_customer_state", table_name="customer")
    op.drop_table("customer")

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        sa.Enum(*CUSTOMER_STATE_VALUES, name="customer_state").drop(bind, checkfirst=True)
