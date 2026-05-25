"""Add ``written_off`` to invoice_state enum (Parity #236).

The bad-debt write-off helper needs a terminal state distinct from
``void``. ``void`` means "this transaction never happened";
``written_off`` means "we gave up collecting and recognized the
outstanding balance as bad-debt expense." Different accounting
treatment, different audit story.

Revision ID: 0063_invoice_written_off
Revises: 0062_saved_report
Create Date: 2026-05-21 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0063_invoice_written_off"
down_revision: str | None = "0062_saved_report"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        # PG enum values can be added but not removed; ``IF NOT EXISTS``
        # keeps this re-runnable.
        op.execute("ALTER TYPE invoice_state ADD VALUE IF NOT EXISTS 'written_off'")
    # SQLite stores enum values as VARCHAR; no DDL needed.


def downgrade() -> None:
    # PG enums can't drop values without recreating the type. We accept
    # the asymmetry — a downgrade would have to leave the value in
    # place. The application-level check constraint isn't widened on
    # downgrade, so this is informational only.
    pass
