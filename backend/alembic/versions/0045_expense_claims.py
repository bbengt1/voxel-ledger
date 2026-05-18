"""expense_claim + expense_claim_line (Phase 8.7, #134)

Creates the ``expense_claim`` and ``expense_claim_line`` tables plus the
``expense_claim_state`` PG enum. Per ops convention (agents.md PG
strict-typing gotcha #1) the enum is NOT pre-created — it's auto-created
by ``op.create_table`` via the column's dialect hook. Booleans use
``sa.false()`` / ``sa.true()`` (gotcha "Boolean defaults"), never
``sa.text("0")``.

Phase 8.7 introduces:

* ``expense_claim`` — the aggregate. Submitted by an employee, routed
  through Phase 4.4 approvals when ``total_amount >= threshold``,
  approved JE posts Dr Expense / Cr Employee-Reimbursable liability, and
  finally reimbursed via a Phase 8.3 ``bill_payment`` FK stamp.
* ``expense_claim_line`` — the lines. Each line references an
  ``expense_category`` (Phase 8.6) for the per-line Dr expense account
  resolution chain. Includes a few columns reserved for Phase 8.8
  rebill-to-customer (``is_billable``, ``customer_id``,
  ``billed_invoice_item_id``, ``markup_percent``) that today are inert.

Revision ID: 0045_expense_claims
Revises: 0044_expense_cat
Create Date: 2026-05-17 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0045_expense_claims"
down_revision: str | None = "0044_expense_cat"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


EXPENSE_CLAIM_STATE_VALUES = (
    "draft",
    "submitted",
    "approved",
    "rejected",
    "reimbursed",
    "cancelled",
)


def upgrade() -> None:
    expense_claim_state_enum = sa.Enum(*EXPENSE_CLAIM_STATE_VALUES, name="expense_claim_state")

    op.create_table(
        "expense_claim",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("claim_number", sa.String(length=32), nullable=False, unique=True),
        sa.Column(
            "submitter_user_id",
            sa.Uuid(),
            sa.ForeignKey("user.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "state",
            expense_claim_state_enum,
            nullable=False,
            server_default="draft",
        ),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "approver_user_id",
            sa.Uuid(),
            sa.ForeignKey("user.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column(
            "total_amount",
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
            "posting_journal_entry_id",
            sa.Uuid(),
            sa.ForeignKey("journal_entry.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "approval_request_id",
            sa.Uuid(),
            sa.ForeignKey("approval_request.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "reimbursement_payment_id",
            sa.Uuid(),
            sa.ForeignKey("bill_payment.id", ondelete="SET NULL"),
            nullable=True,
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
    )
    op.create_index("ix_expense_claim_state", "expense_claim", ["state"])
    op.create_index("ix_expense_claim_submitter_user_id", "expense_claim", ["submitter_user_id"])
    op.create_index(
        "ix_expense_claim_approval_request_id", "expense_claim", ["approval_request_id"]
    )
    op.create_index("ix_expense_claim_created_at_id", "expense_claim", ["created_at", "id"])

    op.create_table(
        "expense_claim_line",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "claim_id",
            sa.Uuid(),
            sa.ForeignKey("expense_claim.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("line_number", sa.Integer(), nullable=False),
        sa.Column(
            "expense_category_id",
            sa.Uuid(),
            sa.ForeignKey("expense_category.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("amount", sa.Numeric(18, 6), nullable=False),
        sa.Column("occurred_on", sa.Date(), nullable=False),
        sa.Column(
            "attachment_id",
            sa.Uuid(),
            sa.ForeignKey("attachment.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "is_billable",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "customer_id",
            sa.Uuid(),
            sa.ForeignKey("customer.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "billed_invoice_item_id",
            sa.Uuid(),
            sa.ForeignKey("invoice_item.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "markup_percent",
            sa.Numeric(7, 4),
            nullable=False,
            server_default=sa.text("0"),
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
        sa.UniqueConstraint("claim_id", "line_number", name="uq_expense_claim_line_claim_line"),
    )
    op.create_index("ix_expense_claim_line_claim_id", "expense_claim_line", ["claim_id"])
    op.create_index(
        "ix_expense_claim_line_expense_category_id",
        "expense_claim_line",
        ["expense_category_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_expense_claim_line_expense_category_id", table_name="expense_claim_line")
    op.drop_index("ix_expense_claim_line_claim_id", table_name="expense_claim_line")
    op.drop_table("expense_claim_line")

    op.drop_index("ix_expense_claim_created_at_id", table_name="expense_claim")
    op.drop_index("ix_expense_claim_approval_request_id", table_name="expense_claim")
    op.drop_index("ix_expense_claim_submitter_user_id", table_name="expense_claim")
    op.drop_index("ix_expense_claim_state", table_name="expense_claim")
    op.drop_table("expense_claim")

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        sa.Enum(*EXPENSE_CLAIM_STATE_VALUES, name="expense_claim_state").drop(bind, checkfirst=True)
