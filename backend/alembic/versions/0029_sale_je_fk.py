"""sale.posting_journal_entry_id FK column (Phase 6.3, #95 follow-up)

Adds a nullable FK column ``posting_journal_entry_id`` on the ``sale``
table that points at the journal entry created when the sale is
confirmed. The COGS service populates this column inside the same
transaction that posts the journal entry, and ``reverse_for_sale`` looks
the entry up via this FK rather than by matching on the journal
entry's description string (which is brittle).

The column is nullable because:

* Draft / cancelled-from-draft sales never had a posting JE.
* On the rare chance any prior-PR sale exists, defensive code in
  ``reverse_for_sale`` raises a clear error rather than silently falling
  back to description scanning.

``ON DELETE SET NULL`` preserves the sale row if a journal entry is ever
hard-deleted (deleting JEs is not a real workflow today — entries are
reversed, not deleted — but the FK should not lock the sale to its
posting entry).

Revision ID: 0029_sale_je_fk
Revises: 0028_sale_consumption_enum
Create Date: 2026-05-15 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0029_sale_je_fk"
down_revision: str | None = "0028_sale_consumption_enum"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "sale",
        sa.Column(
            "posting_journal_entry_id",
            sa.Uuid(),
            sa.ForeignKey("journal_entry.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_sale_posting_journal_entry_id",
        "sale",
        ["posting_journal_entry_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_sale_posting_journal_entry_id", table_name="sale")
    op.drop_column("sale", "posting_journal_entry_id")
