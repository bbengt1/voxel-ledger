"""saved_report table (Parity #237).

Per-user filter preset for any report. The ``filters`` column is an
opaque jsonb blob that the backend never interprets — the frontend
that knows the page is responsible for setting + restoring it. Per-
user scope; no sharing in v1.

Revision ID: 0062_saved_report
Revises: 0061_worker_run_state
Create Date: 2026-05-21 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0062_saved_report"
down_revision: str | None = "0061_worker_run_state"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "saved_report",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "owner_user_id",
            sa.Uuid(),
            sa.ForeignKey("user.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("report_kind", sa.String(length=64), nullable=False),
        sa.Column(
            "filters",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'"),
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
            "owner_user_id",
            "report_kind",
            "name",
            name="uq_saved_report_owner_kind_name",
        ),
    )
    op.create_index(
        "ix_saved_report_owner_kind",
        "saved_report",
        ["owner_user_id", "report_kind"],
    )


def downgrade() -> None:
    op.drop_index("ix_saved_report_owner_kind", table_name="saved_report")
    op.drop_table("saved_report")
