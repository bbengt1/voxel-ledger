"""QBO sync outbox: transactional queue for pushing postings to QBO (#316).

Phase 3 foundation. Epic #312.

Revision ID: 0081_qbo_sync_outbox
Revises: 0080_qbo_master_data_maps
Create Date: 2026-06-08 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from app.models.qbo_sync_outbox import QBO_SYNC_STATUS_VALUES
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0081_qbo_sync_outbox"
down_revision: str | None = "0080_qbo_master_data_maps"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "qbo_sync_outbox",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column("local_id", sa.Uuid(), nullable=False),
        sa.Column("op", sa.String(length=16), nullable=False, server_default="post"),
        sa.Column(
            "status",
            sa.Enum(*QBO_SYNC_STATUS_VALUES, name="qbo_sync_status"),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("request_id", sa.String(length=64), nullable=False),
        sa.Column("payload", sa.JSON().with_variant(JSONB(), "postgresql"), nullable=False),
        sa.Column("qbo_entity_type", sa.String(length=32), nullable=True),
        sa.Column("qbo_id", sa.String(length=64), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "next_attempt_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_qbo_sync_outbox_due", "qbo_sync_outbox", ["status", "next_attempt_at"])
    op.create_index("ix_qbo_sync_outbox_source", "qbo_sync_outbox", ["kind", "local_id"])


def downgrade() -> None:
    op.drop_index("ix_qbo_sync_outbox_source", table_name="qbo_sync_outbox")
    op.drop_index("ix_qbo_sync_outbox_due", table_name="qbo_sync_outbox")
    op.drop_table("qbo_sync_outbox")
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        sa.Enum(*QBO_SYNC_STATUS_VALUES, name="qbo_sync_status").drop(bind, checkfirst=True)
