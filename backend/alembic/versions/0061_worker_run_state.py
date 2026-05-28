"""worker_run_state table + worker_run_status enum (Issue #220).

Per-job durable record of "did this cron actually run, when, with
what outcome". Keyed on ``job_name`` (PK) so we always have one row
per registered worker — the wrapper UPSERTs on entry.

Per agents.md gotcha #1 the new ``worker_run_status`` enum is NOT
pre-created — ``op.create_table`` auto-creates it via the column
dialect hook.

Revision ID: 0061_worker_run_state
Revises: 0060_webhook_inbound_events
Create Date: 2026-05-21 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0061_worker_run_state"
down_revision: str | None = "0060_webhook_inbound_events"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


WORKER_RUN_STATUS_VALUES = ("ok", "failed", "running")


def upgrade() -> None:
    status_enum = sa.Enum(*WORKER_RUN_STATUS_VALUES, name="worker_run_status")

    op.create_table(
        "worker_run_state",
        sa.Column("job_name", sa.String(length=128), primary_key=True),
        sa.Column("last_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_status", status_enum, nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "last_processed",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("last_duration_ms", sa.Integer(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_worker_run_state_status_finished",
        "worker_run_state",
        ["last_status", "last_finished_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_worker_run_state_status_finished", table_name="worker_run_state")
    op.drop_table("worker_run_state")
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("DROP TYPE IF EXISTS worker_run_status")
