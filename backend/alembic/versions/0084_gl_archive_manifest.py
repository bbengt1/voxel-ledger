"""GL archive manifest: audit record of a local-ledger export (#318, Phase 5a).

The down-migration recovery path + decommission prerequisite. One row per
archive run; the CSV/JSON artifacts live on durable storage.

Revision ID: 0084_gl_archive_manifest
Revises: 0083_qbo_local_account_map
Create Date: 2026-06-11 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0084_gl_archive_manifest"
down_revision: str | None = "0083_qbo_local_account_map"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "gl_archive_manifest",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("cutover_date", sa.Date(), nullable=False),
        sa.Column("artifact_dir", sa.String(length=1024), nullable=False),
        sa.Column("row_counts", sa.JSON().with_variant(JSONB(), "postgresql"), nullable=False),
        sa.Column("checksums", sa.JSON().with_variant(JSONB(), "postgresql"), nullable=False),
        sa.Column("total_debits", sa.Numeric(18, 2), nullable=False),
        sa.Column("total_credits", sa.Numeric(18, 2), nullable=False),
        sa.Column("balanced", sa.Boolean(), nullable=False),
        sa.Column("generated_by_user_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(["generated_by_user_id"], ["user.id"], ondelete="SET NULL"),
    )


def downgrade() -> None:
    op.drop_table("gl_archive_manifest")
