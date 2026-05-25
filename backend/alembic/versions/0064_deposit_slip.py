"""deposit_slip + deposit_slip_item + payment.deposit_to_undeposited
(Parity #235).

Backs the undeposited-funds workflow: customer payments can debit a
clearing account instead of the bank, and one ``deposit_slip``
gathers N undeposited payments into a single bank deposit (matches
how the bank statement reports it).

Per agents.md gotcha #1 the new ``deposit_slip_state`` enum is NOT
pre-created — ``op.create_table`` auto-creates it via the column
dialect hook.

Revision ID: 0064_deposit_slip
Revises: 0063_invoice_written_off
Create Date: 2026-05-25 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0064_deposit_slip"
down_revision: str | None = "0063_invoice_written_off"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


DEPOSIT_SLIP_STATE_VALUES = ("draft", "deposited", "reconciled")


def upgrade() -> None:
    state_enum = sa.Enum(*DEPOSIT_SLIP_STATE_VALUES, name="deposit_slip_state")

    op.create_table(
        "deposit_slip",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("slip_number", sa.String(length=32), nullable=False, unique=True),
        sa.Column(
            "bank_account_id",
            sa.Uuid(),
            sa.ForeignKey("account.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("deposit_date", sa.Date(), nullable=False),
        sa.Column("total_amount", sa.Numeric(18, 6), nullable=False, server_default="0"),
        sa.Column("state", state_enum, nullable=False, server_default="draft"),
        sa.Column(
            "posting_journal_entry_id",
            sa.Uuid(),
            sa.ForeignKey("journal_entry.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_by_user_id",
            sa.Uuid(),
            sa.ForeignKey("user.id", ondelete="SET NULL"),
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
    )
    op.create_index(
        "ix_deposit_slip_bank_state",
        "deposit_slip",
        ["bank_account_id", "state"],
    )

    op.create_table(
        "deposit_slip_item",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "deposit_slip_id",
            sa.Uuid(),
            sa.ForeignKey("deposit_slip.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "payment_id",
            sa.Uuid(),
            sa.ForeignKey("payment.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("amount", sa.Numeric(18, 6), nullable=False),
        # A payment can only be on one deposit slip at a time.
        sa.UniqueConstraint("payment_id", name="uq_deposit_slip_item_payment"),
    )
    op.create_index(
        "ix_deposit_slip_item_slip",
        "deposit_slip_item",
        ["deposit_slip_id"],
    )

    op.add_column(
        "payment",
        sa.Column(
            "deposit_to_undeposited",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("payment", "deposit_to_undeposited")
    op.drop_index("ix_deposit_slip_item_slip", table_name="deposit_slip_item")
    op.drop_table("deposit_slip_item")
    op.drop_index("ix_deposit_slip_bank_state", table_name="deposit_slip")
    op.drop_table("deposit_slip")
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("DROP TYPE IF EXISTS deposit_slip_state")
