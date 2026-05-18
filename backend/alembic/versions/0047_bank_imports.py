"""bank import mappings + CSV/OFX parser + bank_transaction (Phase 8.9, #136)

Introduces the ``banking`` bounded context:

* ``bank_import_mapping`` — operator-defined column maps for re-importing
  CSV statements from the same source.
* ``bank_import_run`` — a single import action's summary (filename,
  counts).
* ``bank_transaction`` — the parsed rows. Dedup is enforced by a unique
  constraint on ``(account_id, external_hash)``.

Per agents.md gotcha #1, the three new PG enums (``bank_import_file_kind``,
``bank_transaction_state``, ``bank_amount_sign``) are auto-created by
``op.create_table`` — they are NOT pre-created. Boolean server defaults
use ``sa.true()`` / ``sa.false()`` (gotcha "Boolean defaults").

Revision ID: 0047_bank_imports
Revises: 0046_billable_expenses
Create Date: 2026-05-18 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0047_bank_imports"
down_revision: str | None = "0046_billable_expenses"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


BANK_IMPORT_FILE_KIND_VALUES = ("csv", "ofx")
BANK_TRANSACTION_STATE_VALUES = ("unmatched", "matched", "ignored", "cleared")
BANK_AMOUNT_SIGN_VALUES = ("signed_amount", "debit_credit_columns", "inflow_outflow")


def upgrade() -> None:
    bank_file_kind_enum = sa.Enum(*BANK_IMPORT_FILE_KIND_VALUES, name="bank_import_file_kind")
    bank_txn_state_enum = sa.Enum(*BANK_TRANSACTION_STATE_VALUES, name="bank_transaction_state")
    bank_amount_sign_enum = sa.Enum(*BANK_AMOUNT_SIGN_VALUES, name="bank_amount_sign")

    op.create_table(
        "bank_import_mapping",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column(
            "account_id",
            sa.Uuid(),
            sa.ForeignKey("account.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("file_kind", bank_file_kind_enum, nullable=False),
        sa.Column("column_map", sa.JSON(), nullable=False),
        sa.Column("date_format", sa.String(length=64), nullable=True),
        sa.Column(
            "delimiter",
            sa.String(length=4),
            nullable=False,
            server_default=",",
        ),
        sa.Column(
            "has_header",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column(
            "encoding",
            sa.String(length=32),
            nullable=False,
            server_default="utf-8",
        ),
        sa.Column("amount_sign", bank_amount_sign_enum, nullable=False),
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
        sa.UniqueConstraint("account_id", "name", name="uq_bank_import_mapping_account_name"),
    )
    op.create_index("ix_bank_import_mapping_account_id", "bank_import_mapping", ["account_id"])
    op.create_index("ix_bank_import_mapping_is_active", "bank_import_mapping", ["is_active"])

    op.create_table(
        "bank_import_run",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "account_id",
            sa.Uuid(),
            sa.ForeignKey("account.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "mapping_id",
            sa.Uuid(),
            sa.ForeignKey("bank_import_mapping.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column(
            "imported_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "imported_by_user_id",
            sa.Uuid(),
            sa.ForeignKey("user.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "row_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "inserted_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "duplicate_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "error_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("notes", sa.Text(), nullable=True),
    )
    op.create_index(
        "ix_bank_import_run_account_id_imported_at",
        "bank_import_run",
        ["account_id", sa.text("imported_at DESC")],
    )

    op.create_table(
        "bank_transaction",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "account_id",
            sa.Uuid(),
            sa.ForeignKey("account.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "import_run_id",
            sa.Uuid(),
            sa.ForeignKey("bank_import_run.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "imported_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("occurred_on", sa.Date(), nullable=False),
        sa.Column(
            "description",
            sa.Text(),
            nullable=False,
            server_default="",
        ),
        sa.Column("memo", sa.Text(), nullable=True),
        sa.Column("amount", sa.Numeric(18, 6), nullable=False),
        sa.Column("running_balance", sa.Numeric(18, 6), nullable=True),
        sa.Column("fitid", sa.String(length=255), nullable=True),
        sa.Column("external_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "state",
            bank_txn_state_enum,
            nullable=False,
            server_default="unmatched",
        ),
        sa.Column(
            "matched_journal_line_id",
            sa.Uuid(),
            sa.ForeignKey("journal_line.id", ondelete="SET NULL"),
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
        sa.UniqueConstraint("account_id", "external_hash", name="uq_bank_transaction_account_hash"),
    )
    op.create_index(
        "ix_bank_transaction_account_state",
        "bank_transaction",
        ["account_id", "state"],
    )
    op.create_index(
        "ix_bank_transaction_account_occurred_on",
        "bank_transaction",
        ["account_id", "occurred_on"],
    )


def downgrade() -> None:
    op.drop_index("ix_bank_transaction_account_occurred_on", table_name="bank_transaction")
    op.drop_index("ix_bank_transaction_account_state", table_name="bank_transaction")
    op.drop_table("bank_transaction")

    op.drop_index("ix_bank_import_run_account_id_imported_at", table_name="bank_import_run")
    op.drop_table("bank_import_run")

    op.drop_index("ix_bank_import_mapping_is_active", table_name="bank_import_mapping")
    op.drop_index("ix_bank_import_mapping_account_id", table_name="bank_import_mapping")
    op.drop_table("bank_import_mapping")

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        sa.Enum(*BANK_AMOUNT_SIGN_VALUES, name="bank_amount_sign").drop(bind, checkfirst=True)
        sa.Enum(*BANK_TRANSACTION_STATE_VALUES, name="bank_transaction_state").drop(
            bind, checkfirst=True
        )
        sa.Enum(*BANK_IMPORT_FILE_KIND_VALUES, name="bank_import_file_kind").drop(
            bind, checkfirst=True
        )
