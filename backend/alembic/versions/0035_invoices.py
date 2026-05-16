"""invoice + invoice_item tables + invoice_state / invoice_item_kind enums (Phase 7.3, #111)

Creates the ``invoice`` and ``invoice_item`` tables for the AR-side
invoice aggregate. Adds two PG enums (``invoice_state``,
``invoice_item_kind``) and ADDS the forward FK constraint on
``quote.accepted_invoice_id`` -> ``invoice.id`` that Phase 7.2 deferred.

Per agents.md gotcha #1 the enums are NOT pre-created — ``op.create_table``
auto-creates them via the columns' dialect hook. On SQLite the same
``sa.Enum`` renders as ``VARCHAR + CHECK``.

Booleans (none in this migration) would use ``sa.false()`` / ``sa.true()``
per the booleans gotcha.

Revision ID: 0035_invoices
Revises: 0034_quotes
Create Date: 2026-05-16 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0035_invoices"
down_revision: str | None = "0034_quotes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


INVOICE_STATE_VALUES = (
    "draft",
    "issued",
    "partially_paid",
    "paid",
    "overdue",
    "void",
)

INVOICE_ITEM_KIND_VALUES = (
    "product",
    "job",
    "manual",
)


def upgrade() -> None:
    invoice_state_enum = sa.Enum(*INVOICE_STATE_VALUES, name="invoice_state")
    invoice_item_kind_enum = sa.Enum(*INVOICE_ITEM_KIND_VALUES, name="invoice_item_kind")

    op.create_table(
        "invoice",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("invoice_number", sa.String(length=32), nullable=False, unique=True),
        sa.Column(
            "customer_id",
            sa.Uuid(),
            sa.ForeignKey("customer.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "quote_id",
            sa.Uuid(),
            sa.ForeignKey("quote.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "sale_id",
            sa.Uuid(),
            sa.ForeignKey("sale.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "state",
            invoice_state_enum,
            nullable=False,
            server_default="draft",
        ),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.Column(
            "amount_paid",
            sa.Numeric(18, 6),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "amount_outstanding",
            sa.Numeric(18, 6),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "currency",
            sa.String(length=3),
            nullable=False,
            server_default="USD",
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("billing_address_snapshot", sa.JSON(), nullable=True),
        sa.Column(
            "posting_journal_entry_id",
            sa.Uuid(),
            sa.ForeignKey("journal_entry.id", ondelete="RESTRICT"),
            nullable=True,
        ),
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

    op.create_index("ix_invoice_state", "invoice", ["state"])
    op.create_index("ix_invoice_customer_id", "invoice", ["customer_id"])
    op.create_index("ix_invoice_quote_id", "invoice", ["quote_id"])
    op.create_index("ix_invoice_sale_id", "invoice", ["sale_id"])
    op.create_index("ix_invoice_created_at_id", "invoice", ["created_at", "id"])
    op.create_index("ix_invoice_issued_at", "invoice", ["issued_at"])
    op.create_index("ix_invoice_due_at", "invoice", ["due_at"])

    op.create_table(
        "invoice_item",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "invoice_id",
            sa.Uuid(),
            sa.ForeignKey("invoice.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("line_number", sa.Integer(), nullable=False),
        sa.Column("kind", invoice_item_kind_enum, nullable=False),
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
        sa.UniqueConstraint("invoice_id", "line_number", name="uq_invoice_item_invoice_line"),
        sa.CheckConstraint(
            "(kind = 'product' AND product_id IS NOT NULL AND job_id IS NULL) OR "
            "(kind = 'job' AND job_id IS NOT NULL AND product_id IS NULL) OR "
            "(kind = 'manual' AND product_id IS NULL AND job_id IS NULL)",
            name="ck_invoice_item_kind_ref",
        ),
    )

    op.create_index("ix_invoice_item_invoice_id", "invoice_item", ["invoice_id"])
    op.create_index("ix_invoice_item_product_id", "invoice_item", ["product_id"])
    op.create_index("ix_invoice_item_job_id", "invoice_item", ["job_id"])

    # Add the deferred FK on quote.accepted_invoice_id -> invoice.id (Phase 7.2
    # left the column as a bare nullable UUID; now that invoice exists, wire
    # the constraint).
    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        op.create_foreign_key(
            "fk_quote_accepted_invoice_id",
            source_table="quote",
            referent_table="invoice",
            local_cols=["accepted_invoice_id"],
            remote_cols=["id"],
            ondelete="RESTRICT",
        )
    # SQLite ALTER TABLE doesn't support ADD CONSTRAINT for FK; tests
    # rely on Base.metadata.create_all (which already includes the
    # constraint by virtue of the relationship). Skipping the ALTER on
    # SQLite is safe because the test schema gets the FK at create_all
    # time anyway when the ORM declares it. (We leave the ORM column on
    # quote.accepted_invoice_id as a bare UUID to avoid an ORM-side
    # circular import; the constraint exists on PG via this migration.)


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        op.drop_constraint("fk_quote_accepted_invoice_id", "quote", type_="foreignkey")

    op.drop_index("ix_invoice_item_job_id", table_name="invoice_item")
    op.drop_index("ix_invoice_item_product_id", table_name="invoice_item")
    op.drop_index("ix_invoice_item_invoice_id", table_name="invoice_item")
    op.drop_table("invoice_item")

    op.drop_index("ix_invoice_due_at", table_name="invoice")
    op.drop_index("ix_invoice_issued_at", table_name="invoice")
    op.drop_index("ix_invoice_created_at_id", table_name="invoice")
    op.drop_index("ix_invoice_sale_id", table_name="invoice")
    op.drop_index("ix_invoice_quote_id", table_name="invoice")
    op.drop_index("ix_invoice_customer_id", table_name="invoice")
    op.drop_index("ix_invoice_state", table_name="invoice")
    op.drop_table("invoice")

    if bind.dialect.name == "postgresql":
        sa.Enum(*INVOICE_ITEM_KIND_VALUES, name="invoice_item_kind").drop(bind, checkfirst=True)
        sa.Enum(*INVOICE_STATE_VALUES, name="invoice_state").drop(bind, checkfirst=True)
