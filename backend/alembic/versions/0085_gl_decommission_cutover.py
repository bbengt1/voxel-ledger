"""GL decommission cutover declaration: the Phase-5 hard gate (#318, Phase 5c).

A row records the owner's declaration that the cutover preconditions (clean
reconciliation, balanced archive, synced opening balance) were green; the
destructive sub-phases (5d-5f) refuse without one.

Revision ID: 0085_gl_decommission_cutover
Revises: 0084_gl_archive_manifest
Create Date: 2026-06-11 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0085_gl_decommission_cutover"
down_revision: str | None = "0084_gl_archive_manifest"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "gl_decommission_cutover",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("cutover_date", sa.Date(), nullable=False),
        sa.Column("archive_manifest_id", sa.Uuid(), nullable=False),
        sa.Column("opening_balance_outbox_id", sa.Uuid(), nullable=False),
        sa.Column(
            "readiness_snapshot", sa.JSON().with_variant(JSONB(), "postgresql"), nullable=False
        ),
        sa.Column("declared_by_user_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(
            ["archive_manifest_id"], ["gl_archive_manifest.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["opening_balance_outbox_id"], ["qbo_sync_outbox.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["declared_by_user_id"], ["user.id"], ondelete="SET NULL"),
    )


def downgrade() -> None:
    op.drop_table("gl_decommission_cutover")
