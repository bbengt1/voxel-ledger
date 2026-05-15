"""printer_history_event table (Phase 5.4, #80)

Creates the ``printer_history_event`` table plus the
``printer_event_kind`` PG enum. Per ops convention (see #49), the enum
is NOT pre-created; ``op.create_table`` autocreates the PG type via the
column's dialect hook. On SQLite the same ``sa.Enum`` renders as
``VARCHAR + CHECK``.

down_revision chained onto ``0023_jobs_plates`` at merge time so the
alembic graph stays linear. The parallel Phase 5.2 PR (#87) landed first.

Revision ID: 0024_printer_history
Revises: 0023_jobs_plates
Create Date: 2026-05-15 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0024_printer_history"
down_revision: str | None = "0023_jobs_plates"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


PRINTER_EVENT_KIND_VALUES = (
    "print_started",
    "print_paused",
    "print_resumed",
    "print_completed",
    "print_errored",
    "connected",
    "disconnected",
)


def upgrade() -> None:
    printer_event_kind_enum = sa.Enum(*PRINTER_EVENT_KIND_VALUES, name="printer_event_kind")

    op.create_table(
        "printer_history_event",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "printer_id",
            sa.Uuid(),
            sa.ForeignKey("printer.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("event_kind", printer_event_kind_enum, nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("details", sa.JSON(), nullable=True),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    op.create_index(
        "ix_printer_history_event_printer_occurred",
        "printer_history_event",
        ["printer_id", sa.text("occurred_at DESC")],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_printer_history_event_printer_occurred",
        table_name="printer_history_event",
    )
    op.drop_table("printer_history_event")

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        sa.Enum(*PRINTER_EVENT_KIND_VALUES, name="printer_event_kind").drop(bind, checkfirst=True)
