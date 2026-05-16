"""late_fee_policy table + late_fee_kind enum (Phase 7.6, #114)

Creates the ``late_fee_policy`` table that the daily late-fee worker
uses to compute a debit-note amount against an overdue invoice.

Per agents.md gotcha #1 the ``late_fee_kind`` enum is NOT
pre-created — ``op.create_table`` auto-creates it via the column's
dialect hook. Boolean defaults use ``sa.true()`` per the booleans
gotcha.

Phase 7.6 also relies on an index on ``invoice(state, due_at)`` for
the overdue marker / aging-report scans. Phase 7.3 already created
``ix_invoice_state`` and ``ix_invoice_due_at`` separately, but the
covering compound index isn't there yet; this migration adds it.

Revision ID: 0040_late_fees
Revises: 0036_pay_credits, 0037_recur_inv, 0039_email

This is a merge migration: Phases 7.4, 7.5, 7.7 each landed their own
migration chained directly off 0035_invoices in parallel, leaving the
alembic graph with three heads. This migration unifies them and adds
the late-fee policy table on top.
Create Date: 2026-05-16 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0040_late_fees"
down_revision: tuple[str, ...] = ("0036_pay_credits", "0037_recur_inv", "0039_email")
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
            sa.ForeignKey("customer.id", ondelete="RESTRICT"),
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

    # Covering index on the worker's primary scan predicate
    # (state, due_at). Phase 7.3 created single-column indexes on each;
    # the compound form is what the planner actually wants for
    # ``state IN (...) AND due_at < now()`` (overdue marker) and the
    # AR aging report's bucket sweep.
    op.create_index(
        "ix_invoice_state_due_at",
        "invoice",
        ["state", "due_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_invoice_state_due_at", table_name="invoice")
    op.drop_index("ix_late_fee_policy_is_active", table_name="late_fee_policy")
    op.drop_index("ix_late_fee_policy_customer_id", table_name="late_fee_policy")
    op.drop_table("late_fee_policy")

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        sa.Enum(name="late_fee_kind").drop(bind, checkfirst=True)
