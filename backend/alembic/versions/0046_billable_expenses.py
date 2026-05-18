"""billable expenses on bill_item + indexes (Phase 8.8, #135)

Phase 8.7 (0045) already added all four billable columns to
``expense_claim_line`` (``is_billable``, ``customer_id``,
``billed_invoice_item_id``, ``markup_percent``), with the FK on
``billed_invoice_item_id``. This migration:

* Adds the same four columns to ``bill_item``.
* Adds indexes on the new ``bill_item`` columns.
* Adds indexes on the analogous ``expense_claim_line`` columns
  (Phase 8.7 omitted them).

Per agents.md gotcha "Boolean defaults", ``is_billable`` uses
``sa.false()``, never ``sa.text("0")``.

Revision ID: 0046_billable_expenses
Revises: 0045_expense_claims
Create Date: 2026-05-18 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0046_billable_expenses"
down_revision: str | None = "0045_expense_claims"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "bill_item",
        sa.Column(
            "is_billable",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "bill_item",
        sa.Column("customer_id", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "bill_item",
        sa.Column("billed_invoice_item_id", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "bill_item",
        sa.Column(
            "markup_percent",
            sa.Numeric(7, 4),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.create_foreign_key(
        "fk_bill_item_customer_id",
        "bill_item",
        "customer",
        ["customer_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_bill_item_billed_invoice_item_id",
        "bill_item",
        "invoice_item",
        ["billed_invoice_item_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_bill_item_customer_id", "bill_item", ["customer_id"])
    op.create_index("ix_bill_item_is_billable", "bill_item", ["is_billable"])
    op.create_index(
        "ix_bill_item_billed_invoice_item_id",
        "bill_item",
        ["billed_invoice_item_id"],
    )

    op.create_index(
        "ix_expense_claim_line_customer_id",
        "expense_claim_line",
        ["customer_id"],
    )
    op.create_index(
        "ix_expense_claim_line_is_billable",
        "expense_claim_line",
        ["is_billable"],
    )
    op.create_index(
        "ix_expense_claim_line_billed_invoice_item_id",
        "expense_claim_line",
        ["billed_invoice_item_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_expense_claim_line_billed_invoice_item_id",
        table_name="expense_claim_line",
    )
    op.drop_index(
        "ix_expense_claim_line_is_billable",
        table_name="expense_claim_line",
    )
    op.drop_index(
        "ix_expense_claim_line_customer_id",
        table_name="expense_claim_line",
    )

    op.drop_index("ix_bill_item_billed_invoice_item_id", table_name="bill_item")
    op.drop_index("ix_bill_item_is_billable", table_name="bill_item")
    op.drop_index("ix_bill_item_customer_id", table_name="bill_item")
    op.drop_constraint("fk_bill_item_billed_invoice_item_id", "bill_item", type_="foreignkey")
    op.drop_constraint("fk_bill_item_customer_id", "bill_item", type_="foreignkey")
    op.drop_column("bill_item", "markup_percent")
    op.drop_column("bill_item", "billed_invoice_item_id")
    op.drop_column("bill_item", "customer_id")
    op.drop_column("bill_item", "is_billable")
