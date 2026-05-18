"""expense_category + FK constraints on bill_item / recurring_bill_template_item (8.6, #133)

Creates the ``expense_category`` aggregate (one-level-deep hierarchy via
a nullable self-FK on ``parent_id``) and retro-fits the FK constraints
on the two existing bare-UUID columns:

* ``bill_item.expense_category_id`` (added by Phase 8.2 as a bare UUID)
* ``recurring_bill_template_item.expense_category_id`` (Phase 8.5)

Both FK constraints use ``ondelete=RESTRICT``. The expense-account
validation (account must have ``type='expense'``) and parent-depth
limit (``parent.parent_id IS NULL``) are service-level checks — no DB
constraint enforces them.

Booleans use ``sa.true()`` per agents.md gotcha #1.

Revision ID: 0044_expense_cat
Revises: 0043_recur_bill
Create Date: 2026-05-17 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0044_expense_cat"
down_revision: str | None = "0043_recur_bill"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "expense_category",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column(
            "default_expense_account_id",
            sa.Uuid(),
            sa.ForeignKey("account.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "parent_id",
            sa.Uuid(),
            sa.ForeignKey("expense_category.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column("notes", sa.Text(), nullable=True),
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
        sa.UniqueConstraint("code", name="uq_expense_category_code"),
    )
    op.create_index("ix_expense_category_parent_id", "expense_category", ["parent_id"])
    op.create_index("ix_expense_category_is_active", "expense_category", ["is_active"])

    op.create_foreign_key(
        "fk_bill_item_expense_category_id",
        "bill_item",
        "expense_category",
        ["expense_category_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_recurring_bill_template_item_expense_category_id",
        "recurring_bill_template_item",
        "expense_category",
        ["expense_category_id"],
        ["id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_recurring_bill_template_item_expense_category_id",
        "recurring_bill_template_item",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_bill_item_expense_category_id",
        "bill_item",
        type_="foreignkey",
    )
    op.drop_index("ix_expense_category_is_active", table_name="expense_category")
    op.drop_index("ix_expense_category_parent_id", table_name="expense_category")
    op.drop_table("expense_category")
