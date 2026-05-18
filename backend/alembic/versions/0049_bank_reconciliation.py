"""bank reconciliation + items (Phase 8.11, #138)

Introduces the ``bank_reconciliation`` aggregate — periodic statement
reconciliations the operator opens, ticks off, and finalizes once the
book balance matches the statement. Items denormalize the membership of
``bank_transaction`` rows in a given reconciliation period and carry the
operator's tick-mark.

Inter-account transfers (also Phase 8.11) do NOT introduce a new
aggregate — they are recorded as plain balanced journal entries with a
``banking.InterAccountTransferPosted`` event whose ``aggregate_type`` is
``journal_entry``. No migration required for them.

Per agents.md gotcha #1 the new ``bank_reconciliation_state`` PG enum is
auto-created by ``op.create_table`` — NOT pre-created. Per the booleans
gotcha the items' ``is_cleared`` default uses ``sa.false()``.

The "at most one non-finalized reconciliation per (account_id,
period_end)" rule is enforced by a partial unique index. PG honors the
predicate; SQLite supports partial indexes natively too. Pattern mirrors
``uq_late_fee_policy_active_customer`` in migration 0038.

Revision ID: 0049_bank_reconciliation
Revises: 0048_bank_match_rules
Create Date: 2026-05-18 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0049_bank_reconciliation"
down_revision: str | None = "0048_bank_match_rules"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


BANK_RECONCILIATION_STATE_VALUES = ("in_progress", "balanced", "finalized")


def upgrade() -> None:
    state_enum = sa.Enum(*BANK_RECONCILIATION_STATE_VALUES, name="bank_reconciliation_state")

    op.create_table(
        "bank_reconciliation",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "account_id",
            sa.Uuid(),
            sa.ForeignKey("account.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("statement_ending_balance", sa.Numeric(18, 6), nullable=False),
        sa.Column("book_ending_balance", sa.Numeric(18, 6), nullable=True),
        sa.Column("difference", sa.Numeric(18, 6), nullable=True),
        sa.Column(
            "state",
            state_enum,
            nullable=False,
            server_default="in_progress",
        ),
        sa.Column("finalized_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "finalized_by_user_id",
            sa.Uuid(),
            sa.ForeignKey("user.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("notes", sa.Text(), nullable=True),
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
    op.create_index(
        "ix_bank_reconciliation_account_state",
        "bank_reconciliation",
        ["account_id", "state"],
    )
    op.create_index(
        "ix_bank_reconciliation_period_end",
        "bank_reconciliation",
        ["period_end"],
    )
    # Partial unique index — only one NON-finalized reconciliation per
    # (account, period_end). PG + SQLite both honor the predicate.
    op.create_index(
        "uq_bank_reconciliation_open_period",
        "bank_reconciliation",
        ["account_id", "period_end"],
        unique=True,
        postgresql_where=sa.text("state != 'finalized'"),
        sqlite_where=sa.text("state != 'finalized'"),
    )

    op.create_table(
        "bank_reconciliation_item",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "reconciliation_id",
            sa.Uuid(),
            sa.ForeignKey("bank_reconciliation.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "bank_transaction_id",
            sa.Uuid(),
            sa.ForeignKey("bank_transaction.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "is_cleared",
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
        sa.UniqueConstraint(
            "reconciliation_id",
            "bank_transaction_id",
            name="uq_bank_reconciliation_item_recon_tx",
        ),
    )
    op.create_index(
        "ix_bank_reconciliation_item_reconciliation_id",
        "bank_reconciliation_item",
        ["reconciliation_id"],
    )
    op.create_index(
        "ix_bank_reconciliation_item_bank_transaction_id",
        "bank_reconciliation_item",
        ["bank_transaction_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_bank_reconciliation_item_bank_transaction_id",
        table_name="bank_reconciliation_item",
    )
    op.drop_index(
        "ix_bank_reconciliation_item_reconciliation_id",
        table_name="bank_reconciliation_item",
    )
    op.drop_table("bank_reconciliation_item")

    op.drop_index("uq_bank_reconciliation_open_period", table_name="bank_reconciliation")
    op.drop_index("ix_bank_reconciliation_period_end", table_name="bank_reconciliation")
    op.drop_index("ix_bank_reconciliation_account_state", table_name="bank_reconciliation")
    op.drop_table("bank_reconciliation")

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        sa.Enum(*BANK_RECONCILIATION_STATE_VALUES, name="bank_reconciliation_state").drop(
            bind, checkfirst=True
        )
