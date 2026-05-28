"""webhook_subscription + webhook_delivery (Phase 11.1, #193).

Backs the outbound webhook dispatcher. ``webhook_subscription`` is the
user-configured target (URL + secret + event-type filter).
``webhook_delivery`` is one row per (subscription, event) fan-out,
walked by the every-minute worker.

Per agents.md gotcha #1 the new ``webhook_delivery_status`` enum is NOT
pre-created — ``op.create_table`` auto-creates it via the column dialect
hook.

Revision ID: 0059_webhook_subscriptions
Revises: 0058_ai_insight_summary
Create Date: 2026-05-20 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0059_webhook_subscriptions"
down_revision: str | None = "0058_ai_insight_summary"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


WEBHOOK_DELIVERY_STATUS_VALUES = ("pending", "delivered", "failed", "dead_letter")


def upgrade() -> None:
    status_enum = sa.Enum(*WEBHOOK_DELIVERY_STATUS_VALUES, name="webhook_delivery_status")

    op.create_table(
        "webhook_subscription",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("target_url", sa.Text(), nullable=False),
        sa.Column("secret", sa.String(length=128), nullable=False),
        sa.Column(
            "event_types",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_by_user_id",
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
    )
    op.create_index(
        "ix_webhook_subscription_active",
        "webhook_subscription",
        ["is_active"],
    )

    op.create_table(
        "webhook_delivery",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "subscription_id",
            sa.Uuid(),
            sa.ForeignKey("webhook_subscription.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "event_id",
            sa.Uuid(),
            sa.ForeignKey("event.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_status", status_enum, nullable=False, server_default="pending"),
        sa.Column("last_response_code", sa.Integer(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "next_attempt_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
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
    )
    op.create_index(
        "ix_webhook_delivery_subscription_status",
        "webhook_delivery",
        ["subscription_id", "last_status"],
    )
    op.create_index(
        "ix_webhook_delivery_next_attempt",
        "webhook_delivery",
        ["next_attempt_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_webhook_delivery_next_attempt", table_name="webhook_delivery")
    op.drop_index("ix_webhook_delivery_subscription_status", table_name="webhook_delivery")
    op.drop_table("webhook_delivery")
    op.drop_index("ix_webhook_subscription_active", table_name="webhook_subscription")
    op.drop_table("webhook_subscription")

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("DROP TYPE IF EXISTS webhook_delivery_status")
