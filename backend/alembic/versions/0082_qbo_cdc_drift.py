"""QBO CDC drift records: external edits/deletes to synced entities (#317).

Phase 4a. Epic #312.

Revision ID: 0082_qbo_cdc_drift
Revises: 0081_qbo_sync_outbox
Create Date: 2026-06-10 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from app.models.qbo_cdc_drift import QBO_DRIFT_STATUS_VALUES
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0082_qbo_cdc_drift"
down_revision: str | None = "0081_qbo_sync_outbox"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "qbo_cdc_drift",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("entity_type", sa.String(length=32), nullable=False),
        sa.Column("qbo_id", sa.String(length=64), nullable=False),
        sa.Column("change_type", sa.String(length=16), nullable=False),
        sa.Column("local_kind", sa.String(length=64), nullable=True),
        sa.Column("local_id", sa.Uuid(), nullable=True),
        sa.Column("occurrences", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "status",
            sa.Enum(*QBO_DRIFT_STATUS_VALUES, name="qbo_drift_status"),
            nullable=False,
            server_default="open",
        ),
        sa.Column("detail", sa.JSON().with_variant(JSONB(), "postgresql"), nullable=True),
        sa.Column(
            "first_detected_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "last_detected_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("acknowledged_by_user_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("entity_type", "qbo_id", name="uq_qbo_cdc_drift_entity"),
    )
    op.create_index("ix_qbo_cdc_drift_status", "qbo_cdc_drift", ["status"])


def downgrade() -> None:
    op.drop_index("ix_qbo_cdc_drift_status", table_name="qbo_cdc_drift")
    op.drop_table("qbo_cdc_drift")
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        sa.Enum(*QBO_DRIFT_STATUS_VALUES, name="qbo_drift_status").drop(bind, checkfirst=True)
