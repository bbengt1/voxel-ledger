"""ORM models for outbound webhooks (Phase 11.1, #193).

``WebhookSubscription`` is the user-configured delivery target.
``WebhookDelivery`` is one row per (subscription, event); the worker
walks ``last_status='pending' AND next_attempt_at <= now()``.

Per agents.md gotchas the ``webhook_delivery_status`` enum is created
by the Alembic migration (not pre-created), and the ORM declares it
with ``SAEnum(..., create_type=False, values_callable=...)``.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class WebhookDeliveryStatus(enum.StrEnum):
    PENDING = "pending"
    DELIVERED = "delivered"
    FAILED = "failed"
    DEAD_LETTER = "dead_letter"


WEBHOOK_DELIVERY_STATUS_VALUES: tuple[str, ...] = tuple(m.value for m in WebhookDeliveryStatus)


WEBHOOK_DELIVERY_STATUS_ENUM = SAEnum(
    WebhookDeliveryStatus,
    name="webhook_delivery_status",
    values_callable=lambda enum_cls: [m.value for m in enum_cls],
    create_type=False,
)


class WebhookSubscription(Base):
    __tablename__ = "webhook_subscription"
    __table_args__ = (Index("ix_webhook_subscription_active", "is_active"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    name: Mapped[str] = mapped_column(String(128), nullable=False)
    target_url: Mapped[str] = mapped_column(Text(), nullable=False)
    secret: Mapped[str] = mapped_column(String(128), nullable=False)
    event_types: Mapped[list[str]] = mapped_column(
        JSON(), nullable=False, default=list, server_default="[]"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean(), nullable=False, default=True, server_default="1"
    )

    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class WebhookDelivery(Base):
    __tablename__ = "webhook_delivery"
    __table_args__ = (
        Index(
            "ix_webhook_delivery_subscription_status",
            "subscription_id",
            "last_status",
        ),
        Index("ix_webhook_delivery_next_attempt", "next_attempt_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    subscription_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("webhook_subscription.id", ondelete="CASCADE"), nullable=False
    )
    event_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("event.id", ondelete="SET NULL"), nullable=True
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSON(), nullable=False, default=dict, server_default="{}"
    )

    attempt_count: Mapped[int] = mapped_column(
        Integer(), nullable=False, default=0, server_default="0"
    )
    last_status: Mapped[WebhookDeliveryStatus] = mapped_column(
        WEBHOOK_DELIVERY_STATUS_ENUM,
        nullable=False,
        default=WebhookDeliveryStatus.PENDING,
        server_default="pending",
    )
    last_response_code: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text(), nullable=True)
    next_attempt_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


__all__ = [
    "WEBHOOK_DELIVERY_STATUS_VALUES",
    "WebhookDelivery",
    "WebhookDeliveryStatus",
    "WebhookSubscription",
]
