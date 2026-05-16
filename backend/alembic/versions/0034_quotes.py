"""quote + quote_item tables + quote_state / quote_item_kind enums (Phase 7.2, #110)

Creates the ``quote`` and ``quote_item`` tables for the AR-side
pre-invoice aggregate. Adds two PG enums (``quote_state``,
``quote_item_kind``).

Per agents.md gotcha #1 the enums are NOT pre-created — ``op.create_table``
auto-creates them via the columns' dialect hook. On SQLite the same
``sa.Enum`` renders as ``VARCHAR + CHECK``.

``quote.accepted_invoice_id`` is a NULLABLE UUID column WITHOUT an FK
constraint — Phase 7.3 (#111) adds the FK to ``invoice.id`` once that
table exists. Booleans (none in this migration) would use
``sa.false()`` / ``sa.true()`` per the booleans gotcha.

Revision ID: 0034_quotes
Revises: 0033_customers
Create Date: 2026-05-16 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0034_quotes"
down_revision: str | None = "0033_customers"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


QUOTE_STATE_VALUES = (
    "draft",
    "sent",
    "accepted",
    "declined",
    "expired",
    "cancelled",
)

QUOTE_ITEM_KIND_VALUES = (
    "product",
    "job",
    "manual",
)


def upgrade() -> None:
    quote_state_enum = sa.Enum(*QUOTE_STATE_VALUES, name="quote_state")
    quote_item_kind_enum = sa.Enum(*QUOTE_ITEM_KIND_VALUES, name="quote_item_kind")

    op.create_table(
        "quote",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("quote_number", sa.String(length=32), nullable=False, unique=True),
        sa.Column(
            "customer_id",
            sa.Uuid(),
            sa.ForeignKey("customer.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "state",
            quote_state_enum,
            nullable=False,
            server_default="draft",
        ),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "subtotal",
            sa.Numeric(18, 6),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "discount_amount",
            sa.Numeric(18, 6),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "tax_amount",
            sa.Numeric(18, 6),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "total_amount",
            sa.Numeric(18, 6),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("billing_address_snapshot", sa.JSON(), nullable=True),
        # Forward-declared FK target — Phase 7.3 (#111) adds the FK
        # constraint to invoice.id once that table exists. Nullable UUID
        # column with no constraint today.
        sa.Column("accepted_invoice_id", sa.Uuid(), nullable=True),
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
    )

    op.create_index("ix_quote_state", "quote", ["state"])
    op.create_index("ix_quote_customer_id", "quote", ["customer_id"])
    op.create_index("ix_quote_created_at_id", "quote", ["created_at", "id"])
    op.create_index("ix_quote_issued_at", "quote", ["issued_at"])
    op.create_index("ix_quote_valid_until", "quote", ["valid_until"])

    op.create_table(
        "quote_item",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "quote_id",
            sa.Uuid(),
            sa.ForeignKey("quote.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("line_number", sa.Integer(), nullable=False),
        sa.Column("kind", quote_item_kind_enum, nullable=False),
        sa.Column(
            "product_id",
            sa.Uuid(),
            sa.ForeignKey("product.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "job_id",
            sa.Uuid(),
            sa.ForeignKey("job.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("sku_or_job_number", sa.String(length=64), nullable=True),
        sa.Column(
            "quantity",
            sa.Numeric(18, 6),
            nullable=False,
            server_default=sa.text("1"),
        ),
        sa.Column("unit_price", sa.Numeric(18, 6), nullable=False),
        sa.Column("extended_amount", sa.Numeric(18, 6), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("quote_id", "line_number", name="uq_quote_item_quote_line"),
        sa.CheckConstraint(
            "(kind = 'product' AND product_id IS NOT NULL AND job_id IS NULL) OR "
            "(kind = 'job' AND job_id IS NOT NULL AND product_id IS NULL) OR "
            "(kind = 'manual' AND product_id IS NULL AND job_id IS NULL)",
            name="ck_quote_item_kind_ref",
        ),
    )

    op.create_index("ix_quote_item_quote_id", "quote_item", ["quote_id"])
    op.create_index("ix_quote_item_product_id", "quote_item", ["product_id"])
    op.create_index("ix_quote_item_job_id", "quote_item", ["job_id"])


def downgrade() -> None:
    op.drop_index("ix_quote_item_job_id", table_name="quote_item")
    op.drop_index("ix_quote_item_product_id", table_name="quote_item")
    op.drop_index("ix_quote_item_quote_id", table_name="quote_item")
    op.drop_table("quote_item")

    op.drop_index("ix_quote_valid_until", table_name="quote")
    op.drop_index("ix_quote_issued_at", table_name="quote")
    op.drop_index("ix_quote_created_at_id", table_name="quote")
    op.drop_index("ix_quote_customer_id", table_name="quote")
    op.drop_index("ix_quote_state", table_name="quote")
    op.drop_table("quote")

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        sa.Enum(*QUOTE_ITEM_KIND_VALUES, name="quote_item_kind").drop(bind, checkfirst=True)
        sa.Enum(*QUOTE_STATE_VALUES, name="quote_state").drop(bind, checkfirst=True)
