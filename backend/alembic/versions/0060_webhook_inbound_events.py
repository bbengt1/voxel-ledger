"""webhook_inbound_event table (Phase 11.2, #194).

Tracks every inbound webhook we receive: carrier tracking updates +
marketplace order/refund events. Idempotent on (provider,
external_event_id); a duplicate POST returns 200 + status='duplicate'
without re-applying.

Per agents.md gotcha #1 the new ``webhook_inbound_kind`` and
``webhook_inbound_status`` enums are NOT pre-created — ``op.create_table``
auto-creates them via the column dialect hook.

Revision ID: 0060_webhook_inbound_events
Revises: 0059_webhook_subscriptions
Create Date: 2026-05-20 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0060_webhook_inbound_events"
down_revision: str | None = "0059_webhook_subscriptions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


KIND_VALUES = ("carrier", "marketplace")
STATUS_VALUES = ("received", "applied", "unmatched", "duplicate", "failed", "not_implemented")


def upgrade() -> None:
    kind_enum = sa.Enum(*KIND_VALUES, name="webhook_inbound_kind")
    status_enum = sa.Enum(*STATUS_VALUES, name="webhook_inbound_status")

    op.create_table(
        "webhook_inbound_event",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("kind", kind_enum, nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("external_event_id", sa.String(length=128), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("status", status_enum, nullable=False, server_default="received"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
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
            "provider",
            "external_event_id",
            name="uq_webhook_inbound_event_provider_external_id",
        ),
    )
    op.create_index(
        "ix_webhook_inbound_event_kind_status",
        "webhook_inbound_event",
        ["kind", "status"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_webhook_inbound_event_kind_status", table_name="webhook_inbound_event"
    )
    op.drop_table("webhook_inbound_event")

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("DROP TYPE IF EXISTS webhook_inbound_status")
        op.execute("DROP TYPE IF EXISTS webhook_inbound_kind")
