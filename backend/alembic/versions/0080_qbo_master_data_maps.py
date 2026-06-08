"""QBO master-data mapping: qbo_entity_map + qbo_account_map (#315, epic #312).

Phase 2 storage: links our Customer/Vendor/Product rows to their QBO entities
(with SyncToken), and maps posting-line roles to QBO Account ids.

Revision ID: 0080_qbo_master_data_maps
Revises: 0079_encrypt_oauth_tokens
Create Date: 2026-06-08 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from app.models.qbo_entity_map import QBO_LOCAL_KIND_VALUES

revision: str = "0080_qbo_master_data_maps"
down_revision: str | None = "0079_encrypt_oauth_tokens"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "qbo_entity_map",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "local_kind",
            sa.Enum(*QBO_LOCAL_KIND_VALUES, name="qbo_local_kind"),
            nullable=False,
        ),
        sa.Column("local_id", sa.Uuid(), nullable=False),
        sa.Column("qbo_entity_type", sa.String(length=32), nullable=False),
        sa.Column("qbo_id", sa.String(length=64), nullable=False),
        sa.Column("sync_token", sa.String(length=32), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("local_kind", "local_id", name="ux_qbo_entity_map_local"),
        sa.UniqueConstraint("qbo_entity_type", "qbo_id", name="ux_qbo_entity_map_qbo"),
    )

    op.create_table(
        "qbo_account_map",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("role", sa.String(length=64), nullable=False, unique=True),
        sa.Column("qbo_account_id", sa.String(length=64), nullable=False),
        sa.Column("qbo_account_name", sa.String(length=255), nullable=True),
        sa.Column(
            "updated_by_user_id",
            sa.Uuid(),
            sa.ForeignKey("user.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )


def downgrade() -> None:
    op.drop_table("qbo_account_map")
    op.drop_table("qbo_entity_map")
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        sa.Enum(*QBO_LOCAL_KIND_VALUES, name="qbo_local_kind").drop(bind, checkfirst=True)
