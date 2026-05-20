"""ai_insight_summary table + ai_insight_status enum (Phase 10.7, #182).

Backs the async AI-insights pipeline: an operator (or the dashboard
auto-refresh) ``request`` a summary, the row lands in state
``queued``, the every-15-minute worker picks it up, computes the
structured ``payload`` from the existing report services, runs it
through the configured LLM provider (or a deterministic fallback),
and flips the row to ``ready`` (or ``failed`` with an error message).

Per agents.md gotcha #1 the new ``ai_insight_status`` enum is NOT
pre-created — ``op.create_table`` auto-creates it via the column
dialect hook.

Revision ID: 0058_ai_insight_summary
Revises: 0057_sales_channel_clearing
Create Date: 2026-05-20 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0058_ai_insight_summary"
down_revision: str | None = "0057_sales_channel_clearing"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


AI_INSIGHT_STATUS_VALUES = ("queued", "running", "ready", "failed")


def upgrade() -> None:
    status_enum = sa.Enum(*AI_INSIGHT_STATUS_VALUES, name="ai_insight_status")

    op.create_table(
        "ai_insight_summary",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("scope", sa.String(length=64), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("narrative", sa.Text(), nullable=False, server_default=""),
        sa.Column("model", sa.String(length=64), nullable=True),
        sa.Column("status", status_enum, nullable=False, server_default="queued"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "requested_by_user_id",
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
        sa.CheckConstraint("period_end >= period_start", name="ck_ai_insight_summary_period_range"),
    )
    op.create_index(
        "ix_ai_insight_summary_scope_status",
        "ai_insight_summary",
        ["scope", "status"],
    )
    op.create_index(
        "ix_ai_insight_summary_status_created_at",
        "ai_insight_summary",
        ["status", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_ai_insight_summary_status_created_at", table_name="ai_insight_summary")
    op.drop_index("ix_ai_insight_summary_scope_status", table_name="ai_insight_summary")
    op.drop_table("ai_insight_summary")

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("DROP TYPE IF EXISTS ai_insight_status")
