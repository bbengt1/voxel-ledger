"""ORM model for ``webhook_inbound_event`` (Phase 11.2, #194)."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    DateTime,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class WebhookInboundKind(enum.StrEnum):
    CARRIER = "carrier"
    MARKETPLACE = "marketplace"


class WebhookInboundStatus(enum.StrEnum):
    RECEIVED = "received"
    APPLIED = "applied"
    UNMATCHED = "unmatched"
    DUPLICATE = "duplicate"
    FAILED = "failed"
    NOT_IMPLEMENTED = "not_implemented"


WEBHOOK_INBOUND_KIND_VALUES: tuple[str, ...] = tuple(m.value for m in WebhookInboundKind)
WEBHOOK_INBOUND_STATUS_VALUES: tuple[str, ...] = tuple(
    m.value for m in WebhookInboundStatus
)


WEBHOOK_INBOUND_KIND_ENUM = SAEnum(
    WebhookInboundKind,
    name="webhook_inbound_kind",
    values_callable=lambda enum_cls: [m.value for m in enum_cls],
    create_type=False,
)

WEBHOOK_INBOUND_STATUS_ENUM = SAEnum(
    WebhookInboundStatus,
    name="webhook_inbound_status",
    values_callable=lambda enum_cls: [m.value for m in enum_cls],
    create_type=False,
)


class WebhookInboundEvent(Base):
    __tablename__ = "webhook_inbound_event"
    __table_args__ = (
        UniqueConstraint(
            "provider",
            "external_event_id",
            name="uq_webhook_inbound_event_provider_external_id",
        ),
        Index("ix_webhook_inbound_event_kind_status", "kind", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    kind: Mapped[WebhookInboundKind] = mapped_column(
        WEBHOOK_INBOUND_KIND_ENUM, nullable=False
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    external_event_id: Mapped[str] = mapped_column(String(128), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSON(), nullable=False, default=dict, server_default="{}"
    )

    status: Mapped[WebhookInboundStatus] = mapped_column(
        WEBHOOK_INBOUND_STATUS_ENUM,
        nullable=False,
        default=WebhookInboundStatus.RECEIVED,
        server_default="received",
    )
    error: Mapped[str | None] = mapped_column(Text(), nullable=True)

    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    applied_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
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
    "WEBHOOK_INBOUND_KIND_VALUES",
    "WEBHOOK_INBOUND_STATUS_VALUES",
    "WebhookInboundEvent",
    "WebhookInboundKind",
    "WebhookInboundStatus",
]
