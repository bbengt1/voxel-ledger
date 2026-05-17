"""recurring_bill_template + items + cadence_kind / template_state enums (Phase 8.5, #132)

Creates ``recurring_bill_template`` and ``recurring_bill_template_item``
plus two new PG enums (``recurring_bill_cadence_kind``,
``recurring_bill_template_state``). The line-item ``kind`` column reuses
the existing ``bill_item_kind`` PG enum (created by 0041 with
``create_type=True``) — the dialect-branched ``create_type=False``
pattern is required for the reuse (per agents.md gotcha #2). The new
enums are auto-created via the column hook (gotcha #1). Booleans use
``sa.false()`` per the booleans gotcha.

Revision ID: 0043_recur_bill
Revises: 0042_bill_payments
Create Date: 2026-05-17 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0043_recur_bill"
down_revision: str | None = "0042_bill_payments"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


RECURRING_BILL_CADENCE_KIND_VALUES = (
    "daily",
    "weekly",
    "monthly",
    "quarterly",
    "yearly",
)

RECURRING_BILL_TEMPLATE_STATE_VALUES = (
    "active",
    "paused",
    "cancelled",
)


def upgrade() -> None:
    cadence_kind_enum = sa.Enum(
        *RECURRING_BILL_CADENCE_KIND_VALUES, name="recurring_bill_cadence_kind"
    )
    template_state_enum = sa.Enum(
        *RECURRING_BILL_TEMPLATE_STATE_VALUES, name="recurring_bill_template_state"
    )

    # Reuse the ``bill_item_kind`` enum from Phase 8.2 (0041_bills). Per
    # agents.md gotcha #2 we need the dialect-specific ENUM class with
    # ``create_type=False`` on PG so the auto-create short-circuits.
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        from sqlalchemy.dialects import postgresql

        item_kind_enum = postgresql.ENUM(
            "expense_category",
            "manual",
            name="bill_item_kind",
            create_type=False,
        )
    else:
        item_kind_enum = sa.Enum(
            "expense_category",
            "manual",
            name="bill_item_kind",
            create_type=False,
        )

    op.create_table(
        "recurring_bill_template",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "vendor_id",
            sa.Uuid(),
            sa.ForeignKey("vendor.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("cadence_kind", cadence_kind_enum, nullable=False),
        sa.Column(
            "cadence_interval",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("1"),
        ),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_issue_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_issued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "auto_issue",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "state",
            template_state_enum,
            nullable=False,
            server_default="active",
        ),
        sa.Column("notes", sa.Text(), nullable=True),
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
            "currency",
            sa.String(length=3),
            nullable=False,
            server_default="USD",
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
        sa.CheckConstraint(
            "cadence_interval >= 1",
            name="ck_recurring_bill_template_cadence_interval_positive",
        ),
    )
    op.create_index(
        "ix_recurring_bill_template_vendor_id",
        "recurring_bill_template",
        ["vendor_id"],
    )
    op.create_index(
        "ix_recurring_bill_template_state",
        "recurring_bill_template",
        ["state"],
    )
    op.create_index(
        "ix_recurring_bill_template_next_issue_at",
        "recurring_bill_template",
        ["next_issue_at"],
    )
    op.create_index(
        "ix_recurring_bill_template_created_at_id",
        "recurring_bill_template",
        ["created_at", "id"],
    )

    op.create_table(
        "recurring_bill_template_item",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "template_id",
            sa.Uuid(),
            sa.ForeignKey("recurring_bill_template.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("line_number", sa.Integer(), nullable=False),
        sa.Column("kind", item_kind_enum, nullable=False),
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
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "template_id",
            "line_number",
            name="uq_recurring_bill_template_item_line",
        ),
        sa.CheckConstraint(
            "(kind = 'manual' AND expense_category_id IS NULL) OR "
            "(kind = 'expense_category' AND expense_category_id IS NOT NULL)",
            name="ck_recurring_bill_template_item_kind_ref",
        ),
    )
    op.create_index(
        "ix_recurring_bill_template_item_template_id",
        "recurring_bill_template_item",
        ["template_id"],
    )
    op.create_index(
        "ix_recurring_bill_template_item_expense_category_id",
        "recurring_bill_template_item",
        ["expense_category_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_recurring_bill_template_item_expense_category_id",
        table_name="recurring_bill_template_item",
    )
    op.drop_index(
        "ix_recurring_bill_template_item_template_id",
        table_name="recurring_bill_template_item",
    )
    op.drop_table("recurring_bill_template_item")

    op.drop_index(
        "ix_recurring_bill_template_created_at_id",
        table_name="recurring_bill_template",
    )
    op.drop_index(
        "ix_recurring_bill_template_next_issue_at",
        table_name="recurring_bill_template",
    )
    op.drop_index(
        "ix_recurring_bill_template_state",
        table_name="recurring_bill_template",
    )
    op.drop_index(
        "ix_recurring_bill_template_vendor_id",
        table_name="recurring_bill_template",
    )
    op.drop_table("recurring_bill_template")

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        sa.Enum(*RECURRING_BILL_TEMPLATE_STATE_VALUES, name="recurring_bill_template_state").drop(
            bind, checkfirst=True
        )
        sa.Enum(*RECURRING_BILL_CADENCE_KIND_VALUES, name="recurring_bill_cadence_kind").drop(
            bind, checkfirst=True
        )
