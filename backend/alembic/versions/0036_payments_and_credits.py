"""payments, payment_applications, credit/debit notes, customer credit (Phase 7.4, #112)

Creates the 5 tables and 5 enums supporting AR payments + customer credits:

* ``payment`` + ``payment_application``
* ``credit_note``
* ``debit_note``
* ``customer_credit_balance`` (projection-owned)
* ``customer_credit_transaction`` (append-only ledger)

Enums auto-create per agents.md gotcha #1.

Revision ID: 0036_pay_credits
Revises: 0035_invoices
Create Date: 2026-05-16 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0036_pay_credits"
down_revision: str | None = "0035_invoices"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


PAYMENT_METHOD_VALUES = ("cash", "check", "ach", "wire", "card", "marketplace", "other")
PAYMENT_STATE_VALUES = ("pending", "applied", "cancelled", "bounced")
CREDIT_NOTE_STATE_VALUES = ("draft", "issued", "applied", "cancelled")
DEBIT_NOTE_STATE_VALUES = ("draft", "issued", "applied", "cancelled")
CUSTOMER_CREDIT_KIND_VALUES = ("accrual", "application", "expiration")


def upgrade() -> None:
    payment_method_enum = sa.Enum(*PAYMENT_METHOD_VALUES, name="payment_method")
    payment_state_enum = sa.Enum(*PAYMENT_STATE_VALUES, name="payment_state")
    credit_note_state_enum = sa.Enum(*CREDIT_NOTE_STATE_VALUES, name="credit_note_state")
    debit_note_state_enum = sa.Enum(*DEBIT_NOTE_STATE_VALUES, name="debit_note_state")
    customer_credit_kind_enum = sa.Enum(*CUSTOMER_CREDIT_KIND_VALUES, name="customer_credit_kind")

    # --- payment -----------------------------------------------------------
    op.create_table(
        "payment",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("payment_number", sa.String(length=32), nullable=False, unique=True),
        sa.Column(
            "customer_id",
            sa.Uuid(),
            sa.ForeignKey("customer.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("method", payment_method_enum, nullable=False),
        sa.Column("reference", sa.String(length=128), nullable=True),
        sa.Column("amount", sa.Numeric(18, 6), nullable=False),
        sa.Column(
            "state",
            payment_state_enum,
            nullable=False,
            server_default="pending",
        ),
        sa.Column("notes", sa.Text(), nullable=True),
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
    op.create_index("ix_payment_state", "payment", ["state"])
    op.create_index("ix_payment_customer_id", "payment", ["customer_id"])
    op.create_index("ix_payment_received_at", "payment", ["received_at"])
    op.create_index("ix_payment_created_at_id", "payment", ["created_at", "id"])

    # --- payment_application -----------------------------------------------
    op.create_table(
        "payment_application",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "payment_id",
            sa.Uuid(),
            sa.ForeignKey("payment.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "invoice_id",
            sa.Uuid(),
            sa.ForeignKey("invoice.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("amount", sa.Numeric(18, 6), nullable=False),
        sa.Column(
            "applied_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_payment_application_payment_id", "payment_application", ["payment_id"])
    op.create_index("ix_payment_application_invoice_id", "payment_application", ["invoice_id"])

    # --- credit_note --------------------------------------------------------
    op.create_table(
        "credit_note",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("credit_note_number", sa.String(length=32), nullable=False, unique=True),
        sa.Column(
            "customer_id",
            sa.Uuid(),
            sa.ForeignKey("customer.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "invoice_id",
            sa.Uuid(),
            sa.ForeignKey("invoice.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("reason", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("total_amount", sa.Numeric(18, 6), nullable=False),
        sa.Column(
            "state",
            credit_note_state_enum,
            nullable=False,
            server_default="draft",
        ),
        sa.Column("notes", sa.Text(), nullable=True),
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
    op.create_index("ix_credit_note_state", "credit_note", ["state"])
    op.create_index("ix_credit_note_customer_id", "credit_note", ["customer_id"])
    op.create_index("ix_credit_note_invoice_id", "credit_note", ["invoice_id"])
    op.create_index("ix_credit_note_created_at_id", "credit_note", ["created_at", "id"])

    # --- debit_note ---------------------------------------------------------
    op.create_table(
        "debit_note",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("debit_note_number", sa.String(length=32), nullable=False, unique=True),
        sa.Column(
            "customer_id",
            sa.Uuid(),
            sa.ForeignKey("customer.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "invoice_id",
            sa.Uuid(),
            sa.ForeignKey("invoice.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("reason", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("total_amount", sa.Numeric(18, 6), nullable=False),
        sa.Column(
            "state",
            debit_note_state_enum,
            nullable=False,
            server_default="draft",
        ),
        sa.Column("notes", sa.Text(), nullable=True),
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
    op.create_index("ix_debit_note_state", "debit_note", ["state"])
    op.create_index("ix_debit_note_customer_id", "debit_note", ["customer_id"])
    op.create_index("ix_debit_note_invoice_id", "debit_note", ["invoice_id"])
    op.create_index("ix_debit_note_created_at_id", "debit_note", ["created_at", "id"])

    # --- customer_credit_balance ------------------------------------------
    op.create_table(
        "customer_credit_balance",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "customer_id",
            sa.Uuid(),
            sa.ForeignKey("customer.id", ondelete="RESTRICT"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "available_amount",
            sa.Numeric(18, 6),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    # --- customer_credit_transaction --------------------------------------
    op.create_table(
        "customer_credit_transaction",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "customer_id",
            sa.Uuid(),
            sa.ForeignKey("customer.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("kind", customer_credit_kind_enum, nullable=False),
        sa.Column("amount", sa.Numeric(18, 6), nullable=False),
        sa.Column(
            "source_invoice_id",
            sa.Uuid(),
            sa.ForeignKey("invoice.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "source_refund_id",
            sa.Uuid(),
            sa.ForeignKey("refund.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "source_payment_id",
            sa.Uuid(),
            sa.ForeignKey("payment.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "applied_to_invoice_id",
            sa.Uuid(),
            sa.ForeignKey("invoice.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_customer_credit_transaction_customer_id",
        "customer_credit_transaction",
        ["customer_id"],
    )
    op.create_index(
        "ix_customer_credit_transaction_created_at_id",
        "customer_credit_transaction",
        ["created_at", "id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_customer_credit_transaction_created_at_id",
        table_name="customer_credit_transaction",
    )
    op.drop_index(
        "ix_customer_credit_transaction_customer_id",
        table_name="customer_credit_transaction",
    )
    op.drop_table("customer_credit_transaction")
    op.drop_table("customer_credit_balance")

    op.drop_index("ix_debit_note_created_at_id", table_name="debit_note")
    op.drop_index("ix_debit_note_invoice_id", table_name="debit_note")
    op.drop_index("ix_debit_note_customer_id", table_name="debit_note")
    op.drop_index("ix_debit_note_state", table_name="debit_note")
    op.drop_table("debit_note")

    op.drop_index("ix_credit_note_created_at_id", table_name="credit_note")
    op.drop_index("ix_credit_note_invoice_id", table_name="credit_note")
    op.drop_index("ix_credit_note_customer_id", table_name="credit_note")
    op.drop_index("ix_credit_note_state", table_name="credit_note")
    op.drop_table("credit_note")

    op.drop_index("ix_payment_application_invoice_id", table_name="payment_application")
    op.drop_index("ix_payment_application_payment_id", table_name="payment_application")
    op.drop_table("payment_application")

    op.drop_index("ix_payment_created_at_id", table_name="payment")
    op.drop_index("ix_payment_received_at", table_name="payment")
    op.drop_index("ix_payment_customer_id", table_name="payment")
    op.drop_index("ix_payment_state", table_name="payment")
    op.drop_table("payment")

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        sa.Enum(*CUSTOMER_CREDIT_KIND_VALUES, name="customer_credit_kind").drop(
            bind, checkfirst=True
        )
        sa.Enum(*DEBIT_NOTE_STATE_VALUES, name="debit_note_state").drop(bind, checkfirst=True)
        sa.Enum(*CREDIT_NOTE_STATE_VALUES, name="credit_note_state").drop(bind, checkfirst=True)
        sa.Enum(*PAYMENT_STATE_VALUES, name="payment_state").drop(bind, checkfirst=True)
        sa.Enum(*PAYMENT_METHOD_VALUES, name="payment_method").drop(bind, checkfirst=True)
