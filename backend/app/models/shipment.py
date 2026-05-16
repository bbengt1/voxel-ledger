"""ORM model for ``shipment`` (Phase 6.6, #98).

A shipment is the system-of-record for "this sale will be delivered to
this address by this carrier with this label." Lifecycle:

    pending -> label_purchased -> shipped -> delivered
    (any of the above) -> cancelled
    delivered -> returned

``state`` is a PG enum (``shipment_state``) auto-created by the 0030
migration. Per agents.md PG strict-typing gotcha #3, the ORM declares it
with ``SAEnum(create_type=False)`` so PG comparisons stay typed.

The ``ship_from`` and ``ship_to`` columns are snapshotted as JSON at
shipment-create time so a later edit to the shop address (or the
customer-record address) doesn't retroactively rewrite already-labeled
shipments.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    Text,
    func,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class ShipmentState(enum.StrEnum):
    PENDING = "pending"
    LABEL_PURCHASED = "label_purchased"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    RETURNED = "returned"
    CANCELLED = "cancelled"


SHIPMENT_STATE_VALUES: tuple[str, ...] = tuple(m.value for m in ShipmentState)


SHIPMENT_STATE_ENUM = SAEnum(
    ShipmentState,
    name="shipment_state",
    values_callable=lambda enum_cls: [m.value for m in enum_cls],
    create_type=False,
)


class Shipment(Base):
    __tablename__ = "shipment"
    __table_args__ = (
        Index("ix_shipment_sale_id", "sale_id"),
        Index("ix_shipment_state", "state"),
        Index("ix_shipment_tracking_number", "tracking_number"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    sale_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sale.id", ondelete="CASCADE"), nullable=False
    )

    state: Mapped[ShipmentState] = mapped_column(
        SHIPMENT_STATE_ENUM,
        nullable=False,
        default=ShipmentState.PENDING,
        server_default="pending",
    )

    carrier: Mapped[str] = mapped_column(Text(), nullable=False)
    service_level: Mapped[str | None] = mapped_column(Text(), nullable=True)
    tracking_number: Mapped[str | None] = mapped_column(Text(), nullable=True)
    tracking_url: Mapped[str | None] = mapped_column(Text(), nullable=True)
    label_pdf_storage_key: Mapped[str | None] = mapped_column(Text(), nullable=True)
    cost_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 6), nullable=False, default=Decimal("0"), server_default="0"
    )

    weight_grams: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    dimensions_cm: Mapped[dict[str, Any] | None] = mapped_column(JSON(), nullable=True)

    ship_from: Mapped[dict[str, Any]] = mapped_column(JSON(), nullable=False)
    ship_to: Mapped[dict[str, Any]] = mapped_column(JSON(), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
