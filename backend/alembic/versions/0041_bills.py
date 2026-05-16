"""bill + bill_item tables + bill_state / bill_item_kind enums (Phase 8.2, #129)

Creates the ``bill`` and ``bill_item`` tables for the AP-side bill
aggregate — the direct AP mirror of Phase 7.3's ``invoice``. Adds two
PG enums (``bill_state``, ``bill_item_kind``).

Per agents.md gotcha #1 the enums are NOT pre-created — ``op.create_table``
auto-creates them via the columns' dialect hook. On SQLite the same
``sa.Enum`` renders as ``VARCHAR + CHECK``.

``expense_category_id`` is a bare ``sa.Uuid`` (no FK) — Phase 8.6 adds
the ``expense_category`` table and will retro-fit the FK constraint.

Revision ID: 0041_bills
Revises: 0040_vendors
Create Date: 2026-05-16 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0041_bills"
down_revision: str | None = "0040_vendors"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


BILL_STATE_VALUES = (
    "draft",
    "issued",
    "partially_paid",
    "paid",
    "overdue",
    "void",
)

BILL_ITEM_KIND_VALUES = (
    "expense_category",
    "manual",
)


def upgrade() -> None:
    bill_state_enum = sa.Enum(*BILL_STATE_VALUES, name="bill_state")
    bill_item_kind_enum = sa.Enum(*BILL_ITEM_KIND_VALUES, name="bill_item_kind")

    op.create_table(
        "bill",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("bill_number", sa.String(length=32), nullable=False, unique=True),
        sa.Column(
            "vendor_id",
            sa.Uuid(),
            sa.ForeignKey("vendor.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "state",
            bill_state_enum,
            nullable=False,
            server_default="draft",
        ),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("vendor_invoice_number", sa.String(length=64), nullable=True),
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
        sa.Column("last_late_fee_applied_at", sa.DateTime(timezone=True), nullable=True),
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

    op.create_index("ix_bill_state", "bill", ["state"])
    op.create_index("ix_bill_vendor_id", "bill", ["vendor_id"])
    op.create_index("ix_bill_created_at_id", "bill", ["created_at", "id"])
    op.create_index("ix_bill_issued_at", "bill", ["issued_at"])
    op.create_index("ix_bill_due_at", "bill", ["due_at"])
    op.create_index("ix_bill_state_due_at", "bill", ["state", "due_at"])

    op.create_table(
        "bill_item",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "bill_id",
            sa.Uuid(),
            sa.ForeignKey("bill.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("line_number", sa.Integer(), nullable=False),
        sa.Column("kind", bill_item_kind_enum, nullable=False),
        # No FK today; Phase 8.6 lands the expense_category table and
        # retro-fits the constraint.
        sa.Column("expense_category_id", sa.Uuid(), nullable=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("vendor_sku", sa.String(length=64), nullable=True),
        sa.Column(
            "quantity",
            sa.Numeric(18, 6),
            nullable=False,
            server_default=sa.text("1"),
        ),
        sa.Column("unit_price", sa.Numeric(18, 6), nullable=False),
        sa.Column("extended_amount", sa.Numeric(18, 6), nullable=False),
        sa.Column(
            "expense_account_id_override",
            sa.Uuid(),
            sa.ForeignKey("account.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("bill_id", "line_number", name="uq_bill_item_bill_line"),
        sa.CheckConstraint(
            "(kind = 'expense_category' AND expense_category_id IS NOT NULL) OR "
            "(kind = 'manual')",
            name="ck_bill_item_kind_ref",
        ),
    )

    op.create_index("ix_bill_item_bill_id", "bill_item", ["bill_id"])
    op.create_index("ix_bill_item_expense_category_id", "bill_item", ["expense_category_id"])


def downgrade() -> None:
    op.drop_index("ix_bill_item_expense_category_id", table_name="bill_item")
    op.drop_index("ix_bill_item_bill_id", table_name="bill_item")
    op.drop_table("bill_item")

    op.drop_index("ix_bill_state_due_at", table_name="bill")
    op.drop_index("ix_bill_due_at", table_name="bill")
    op.drop_index("ix_bill_issued_at", table_name="bill")
    op.drop_index("ix_bill_created_at_id", table_name="bill")
    op.drop_index("ix_bill_vendor_id", table_name="bill")
    op.drop_index("ix_bill_state", table_name="bill")
    op.drop_table("bill")

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        sa.Enum(*BILL_ITEM_KIND_VALUES, name="bill_item_kind").drop(bind, checkfirst=True)
        sa.Enum(*BILL_STATE_VALUES, name="bill_state").drop(bind, checkfirst=True)
