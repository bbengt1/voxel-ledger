"""audit_log read-model table

Creates the ``audit_log`` projection table populated by the wildcard
audit projection (#24). One row per event; denormalizes actor/email/role
and a per-event-type ``payload_excerpt`` whitelist so the audit query API
can serve fast filtered reads without touching the event log directly.

Revision ID: 0006_audit_log
Revises: 0005_reference_sequence
Create Date: 2026-05-14 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import INET, JSONB

revision: str = "0006_audit_log"
down_revision: str | None = "0005_reference_sequence"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    is_pg = bind.dialect.name == "postgresql"

    excerpt_type = JSONB() if is_pg else sa.JSON()
    ip_type = INET() if is_pg else sa.String(length=64)

    op.create_table(
        "audit_log",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "event_id",
            sa.Uuid(),
            sa.ForeignKey("event.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("event_position", sa.BigInteger(), nullable=False, unique=True),
        sa.Column("event_type", sa.String(length=255), nullable=False),
        sa.Column(
            "actor_user_id",
            sa.Uuid(),
            sa.ForeignKey("user.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("actor_email", sa.String(length=255), nullable=True),
        sa.Column("actor_role", sa.String(length=32), nullable=True),
        sa.Column("aggregate_type", sa.String(length=255), nullable=False),
        sa.Column("aggregate_id", sa.Uuid(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("ip_address", ip_type, nullable=True),
        sa.Column("payload_excerpt", excerpt_type, nullable=True),
    )

    op.create_index(
        "ix_audit_log_position_desc",
        "audit_log",
        [sa.text("event_position DESC")],
    )
    op.create_index(
        "ix_audit_log_actor_position",
        "audit_log",
        ["actor_user_id", sa.text("event_position DESC")],
    )
    op.create_index(
        "ix_audit_log_event_type_position",
        "audit_log",
        ["event_type", sa.text("event_position DESC")],
    )
    op.create_index(
        "ix_audit_log_aggregate_position",
        "audit_log",
        ["aggregate_type", "aggregate_id", sa.text("event_position DESC")],
    )


def downgrade() -> None:
    op.drop_index("ix_audit_log_aggregate_position", table_name="audit_log")
    op.drop_index("ix_audit_log_event_type_position", table_name="audit_log")
    op.drop_index("ix_audit_log_actor_position", table_name="audit_log")
    op.drop_index("ix_audit_log_position_desc", table_name="audit_log")
    op.drop_table("audit_log")
