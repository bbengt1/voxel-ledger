"""journal_entry / journal_line / account_balance (Phase 4.2, #65)

Adds the double-entry tables and the running-balance projection table.
Both ``journal_entry`` and ``journal_line`` get PG ``BEFORE UPDATE OR
DELETE`` immutability triggers; the journal_entry trigger has a narrow
carve-out that allows flipping ``is_reversed`` from false to true
(everything else on the row must remain identical). SQLite skips the
triggers entirely — application code never mutates these rows, and the
immutability assertion is covered by a PG integration test.

Boolean ``server_default``s use ``sa.false()`` per #49. No new ENUM
types are introduced.

Revision ID: 0018_journal_entries
Revises: 0017_accounts
Create Date: 2026-05-14 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0018_journal_entries"
down_revision: str | None = "0017_accounts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


JE_IMMUTABILITY_FN = "journal_entry_immutability_check"
JE_IMMUTABILITY_TRIGGER = "journal_entry_immutability_trg"
JL_IMMUTABILITY_FN = "journal_line_immutability_check"
JL_IMMUTABILITY_TRIGGER = "journal_line_immutability_trg"


def upgrade() -> None:
    bind = op.get_bind()
    is_pg = bind.dialect.name == "postgresql"

    op.create_table(
        "journal_entry",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("entry_number", sa.String(length=64), nullable=False, unique=True),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=False),
        # period_id is a bare UUID column today; #4.3 will add the FK +
        # NOT NULL constraint once the period aggregate exists.
        sa.Column("period_id", sa.Uuid(), nullable=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("source_event_id", sa.Uuid(), nullable=True),
        sa.Column(
            "actor_user_id",
            sa.Uuid(),
            sa.ForeignKey("user.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "is_reversed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "reversal_of_entry_id",
            sa.Uuid(),
            sa.ForeignKey("journal_entry.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_journal_entry_posted_at_number",
        "journal_entry",
        ["posted_at", "entry_number"],
    )

    op.create_table(
        "journal_line",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "entry_id",
            sa.Uuid(),
            sa.ForeignKey("journal_entry.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "account_id",
            sa.Uuid(),
            sa.ForeignKey("account.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "debit",
            sa.Numeric(18, 6),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "credit",
            sa.Numeric(18, 6),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("line_number", sa.Integer(), nullable=False),
        sa.Column("memo", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "(debit > 0 AND credit = 0) OR (credit > 0 AND debit = 0)",
            name="ck_journal_line_debit_xor_credit",
        ),
    )
    op.create_index("ix_journal_line_entry_id", "journal_line", ["entry_id"])
    op.create_index(
        "ix_journal_line_account_entry",
        "journal_line",
        ["account_id", "entry_id"],
    )

    op.create_table(
        "account_balance",
        sa.Column(
            "account_id",
            sa.Uuid(),
            sa.ForeignKey("account.id", ondelete="RESTRICT"),
            primary_key=True,
        ),
        sa.Column(
            "total_debits",
            sa.Numeric(18, 6),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "total_credits",
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

    if is_pg:
        # journal_entry trigger: allow only the is_reversed false→true flip.
        op.execute(
            f"""
            CREATE OR REPLACE FUNCTION {JE_IMMUTABILITY_FN}()
            RETURNS trigger AS $$
            BEGIN
              IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION
                  'journal_entry is append-only; deletion is not allowed';
              END IF;
              IF NOT (
                NEW.id IS NOT DISTINCT FROM OLD.id
                AND NEW.entry_number IS NOT DISTINCT FROM OLD.entry_number
                AND NEW.posted_at IS NOT DISTINCT FROM OLD.posted_at
                AND NEW.period_id IS NOT DISTINCT FROM OLD.period_id
                AND NEW.description IS NOT DISTINCT FROM OLD.description
                AND NEW.source_event_id IS NOT DISTINCT FROM OLD.source_event_id
                AND NEW.actor_user_id IS NOT DISTINCT FROM OLD.actor_user_id
                AND NEW.reversal_of_entry_id
                    IS NOT DISTINCT FROM OLD.reversal_of_entry_id
                AND OLD.is_reversed = false
                AND NEW.is_reversed = true
              ) THEN
                RAISE EXCEPTION
                  'journal_entry is append-only; only the is_reversed '
                  'flag may be updated from false to true';
              END IF;
              RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;
            """
        )
        op.execute(
            f"""
            CREATE TRIGGER {JE_IMMUTABILITY_TRIGGER}
            BEFORE UPDATE OR DELETE ON journal_entry
            FOR EACH ROW EXECUTE FUNCTION {JE_IMMUTABILITY_FN}();
            """
        )

        # journal_line trigger: no carve-out.
        op.execute(
            f"""
            CREATE OR REPLACE FUNCTION {JL_IMMUTABILITY_FN}()
            RETURNS trigger AS $$
            BEGIN
              RAISE EXCEPTION
                'journal_line is append-only (op=%, line_id=%)',
                TG_OP, COALESCE(OLD.id, NEW.id);
            END;
            $$ LANGUAGE plpgsql;
            """
        )
        op.execute(
            f"""
            CREATE TRIGGER {JL_IMMUTABILITY_TRIGGER}
            BEFORE UPDATE OR DELETE ON journal_line
            FOR EACH ROW EXECUTE FUNCTION {JL_IMMUTABILITY_FN}();
            """
        )


def downgrade() -> None:
    bind = op.get_bind()
    is_pg = bind.dialect.name == "postgresql"

    if is_pg:
        op.execute(f"DROP TRIGGER IF EXISTS {JL_IMMUTABILITY_TRIGGER} ON journal_line")
        op.execute(f"DROP FUNCTION IF EXISTS {JL_IMMUTABILITY_FN}()")
        op.execute(f"DROP TRIGGER IF EXISTS {JE_IMMUTABILITY_TRIGGER} ON journal_entry")
        op.execute(f"DROP FUNCTION IF EXISTS {JE_IMMUTABILITY_FN}()")

    op.drop_table("account_balance")

    op.drop_index("ix_journal_line_account_entry", table_name="journal_line")
    op.drop_index("ix_journal_line_entry_id", table_name="journal_line")
    op.drop_table("journal_line")

    op.drop_index("ix_journal_entry_posted_at_number", table_name="journal_entry")
    op.drop_table("journal_entry")
