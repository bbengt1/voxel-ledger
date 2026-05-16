"""bill_payment + bill_payment_application (Phase 8.3, #130)

Mirrors the AP-side payment + applications pair of the AR
``payment`` / ``payment_application`` tables (Phase 7.4, #112).
Posting direction is reversed at the service layer (Dr AP / Cr Bank).

Enums auto-create per agents.md gotcha #1.

Revision ID: 0042_bill_payments
Revises: 0041_bills
Create Date: 2026-05-16 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0042_bill_payments"
down_revision: str | None = "0041_bills"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


BILL_PAYMENT_METHOD_VALUES = ("cash", "check", "ach", "wire", "card", "other")
BILL_PAYMENT_STATE_VALUES = ("pending", "posted", "bounced", "cancelled")


def upgrade() -> None:
    bill_payment_method_enum = sa.Enum(*BILL_PAYMENT_METHOD_VALUES, name="bill_payment_method")
    bill_payment_state_enum = sa.Enum(*BILL_PAYMENT_STATE_VALUES, name="bill_payment_state")

    # --- bill_payment ------------------------------------------------------
    op.create_table(
        "bill_payment",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("payment_number", sa.String(length=32), nullable=False, unique=True),
        sa.Column(
            "vendor_id",
            sa.Uuid(),
            sa.ForeignKey("vendor.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("method", bill_payment_method_enum, nullable=False),
        sa.Column("amount", sa.Numeric(18, 6), nullable=False),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("reference_number", sa.String(length=64), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "state",
            bill_payment_state_enum,
            nullable=False,
            server_default="pending",
        ),
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
    op.create_index("ix_bill_payment_state", "bill_payment", ["state"])
    op.create_index("ix_bill_payment_vendor_id", "bill_payment", ["vendor_id"])
    op.create_index("ix_bill_payment_occurred_at", "bill_payment", ["occurred_at"])
    op.create_index("ix_bill_payment_created_at_id", "bill_payment", ["created_at", "id"])
    # Partial unique index for (vendor_id, reference_number) where set.
    op.create_index(
        "uq_bill_payment_vendor_reference",
        "bill_payment",
        ["vendor_id", "reference_number"],
        unique=True,
        postgresql_where=sa.text("reference_number IS NOT NULL"),
        sqlite_where=sa.text("reference_number IS NOT NULL"),
    )

    # --- bill_payment_application -----------------------------------------
    op.create_table(
        "bill_payment_application",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "bill_payment_id",
            sa.Uuid(),
            sa.ForeignKey("bill_payment.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "bill_id",
            sa.Uuid(),
            sa.ForeignKey("bill.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("amount_applied", sa.Numeric(18, 6), nullable=False),
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
            "bill_payment_id", "bill_id", name="uq_bill_payment_application_payment_bill"
        ),
    )
    op.create_index(
        "ix_bill_payment_application_bill_payment_id",
        "bill_payment_application",
        ["bill_payment_id"],
    )
    op.create_index(
        "ix_bill_payment_application_bill_id",
        "bill_payment_application",
        ["bill_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_bill_payment_application_bill_id", table_name="bill_payment_application")
    op.drop_index(
        "ix_bill_payment_application_bill_payment_id", table_name="bill_payment_application"
    )
    op.drop_table("bill_payment_application")

    op.drop_index("uq_bill_payment_vendor_reference", table_name="bill_payment")
    op.drop_index("ix_bill_payment_created_at_id", table_name="bill_payment")
    op.drop_index("ix_bill_payment_occurred_at", table_name="bill_payment")
    op.drop_index("ix_bill_payment_vendor_id", table_name="bill_payment")
    op.drop_index("ix_bill_payment_state", table_name="bill_payment")
    op.drop_table("bill_payment")

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        sa.Enum(*BILL_PAYMENT_STATE_VALUES, name="bill_payment_state").drop(bind, checkfirst=True)
        sa.Enum(*BILL_PAYMENT_METHOD_VALUES, name="bill_payment_method").drop(bind, checkfirst=True)
