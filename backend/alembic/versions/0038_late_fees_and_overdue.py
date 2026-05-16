"""late_fee_policy table + late_fee_kind enum + invoice late-fee tracking (Phase 7.6, #114).

Creates the ``late_fee_policy`` table (per-customer or global overdue-fee
configuration) plus the ``late_fee_kind`` PG enum
(``percent_of_outstanding`` / ``flat`` / ``compound_percent``). Adds two
columns to ``invoice`` to support idempotent worker re-runs:

* ``last_late_fee_applied_at`` — wall clock of the most recent fee
  application; the worker uses this together with the policy's
  ``compound_interval_days`` to decide whether to apply again.
* (a composite ``ix_invoice_state_due_at`` index is added on top of the
  existing single-column indexes so the overdue scan stays cheap as the
  invoice table grows.)

Also merges the three sibling heads from Phase 7 (0036, 0037, 0039) into
a single linear history at 0038.

Per agents.md gotcha #1 the new ``late_fee_kind`` enum is NOT pre-created
— ``op.create_table`` auto-creates it via the columns' dialect hook. Per
the booleans gotcha the policy's ``is_active`` default uses ``sa.true()``.

Revision ID: 0038_late_fees
Revises: 0036_pay_credits, 0037_recur_inv, 0039_email
Create Date: 2026-05-16 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0038_late_fees"
down_revision: tuple[str, ...] | str | None = (
    "0036_pay_credits",
    "0037_recur_inv",
    "0039_email",
)
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


LATE_FEE_KIND_VALUES = (
    "percent_of_outstanding",
    "flat",
    "compound_percent",
)


def upgrade() -> None:
    late_fee_kind_enum = sa.Enum(*LATE_FEE_KIND_VALUES, name="late_fee_kind")

    op.create_table(
        "late_fee_policy",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "customer_id",
            sa.Uuid(),
            sa.ForeignKey("customer.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("kind", late_fee_kind_enum, nullable=False),
        sa.Column("amount", sa.Numeric(18, 6), nullable=False),
        sa.Column(
            "grace_period_days",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "apply_after_days",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("30"),
        ),
        sa.Column(
            "compound_interval_days",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("30"),
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column("notes", sa.Text(), nullable=True),
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
        sa.CheckConstraint(
            "amount >= 0",
            name="ck_late_fee_policy_amount_nonneg",
        ),
        sa.CheckConstraint(
            "grace_period_days >= 0",
            name="ck_late_fee_policy_grace_nonneg",
        ),
        sa.CheckConstraint(
            "apply_after_days >= 0",
            name="ck_late_fee_policy_apply_after_nonneg",
        ),
        sa.CheckConstraint(
            "compound_interval_days >= 1",
            name="ck_late_fee_policy_compound_interval_positive",
        ),
    )
    op.create_index(
        "ix_late_fee_policy_customer_id",
        "late_fee_policy",
        ["customer_id"],
    )
    op.create_index(
        "ix_late_fee_policy_is_active",
        "late_fee_policy",
        ["is_active"],
    )
    # A unique partial index — only one ACTIVE global (null customer) policy at
    # a time, and only one ACTIVE per-customer policy per customer. PG-only
    # (SQLite ignores the partial predicate but enforces the column tuple).
    op.create_index(
        "uq_late_fee_policy_active_customer",
        "late_fee_policy",
        ["customer_id"],
        unique=True,
        postgresql_where=sa.text("is_active"),
        sqlite_where=sa.text("is_active"),
    )

    op.add_column(
        "invoice",
        sa.Column(
            "last_late_fee_applied_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_invoice_state_due_at",
        "invoice",
        ["state", "due_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_invoice_state_due_at", table_name="invoice")
    op.drop_column("invoice", "last_late_fee_applied_at")

    op.drop_index("uq_late_fee_policy_active_customer", table_name="late_fee_policy")
    op.drop_index("ix_late_fee_policy_is_active", table_name="late_fee_policy")
    op.drop_index("ix_late_fee_policy_customer_id", table_name="late_fee_policy")
    op.drop_table("late_fee_policy")

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        sa.Enum(*LATE_FEE_KIND_VALUES, name="late_fee_kind").drop(bind, checkfirst=True)
