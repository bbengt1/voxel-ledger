"""ORM model for the ``inventory_on_hand`` table (Phase 3.3, #52).

One row per ``(entity_kind, entity_id, location_id)`` triple. The
``on_hand`` value is the running sum of signed quantities from the
``inventory_transaction`` ledger, maintained by the
``inventory_on_hand`` projection. Service code never writes this table
directly — projections own it.

The composite unique constraint is the upsert key. The projection uses
``INSERT ... ON CONFLICT (entity_kind, entity_id, location_id) DO
UPDATE`` so a TransactionRecorded event either creates the row or
accumulates into the existing one atomically.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Index, Numeric, UniqueConstraint, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.inventory_transaction import INVENTORY_ENTITY_KIND_VALUES

INVENTORY_ENTITY_KIND_ENUM = SAEnum(
    *INVENTORY_ENTITY_KIND_VALUES,
    name="inventory_entity_kind",
    native_enum=True,
    create_type=False,
)


class InventoryOnHand(Base):
    __tablename__ = "inventory_on_hand"
    __table_args__ = (
        UniqueConstraint(
            "entity_kind",
            "entity_id",
            "location_id",
            name="uq_inventory_on_hand_entity_location",
        ),
        Index(
            "ix_inventory_on_hand_entity",
            "entity_kind",
            "entity_id",
        ),
        Index(
            "ix_inventory_on_hand_location",
            "location_id",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    entity_kind: Mapped[str] = mapped_column(INVENTORY_ENTITY_KIND_ENUM, nullable=False)
    # Polymorphic ref — no FK by design (matches inventory_transaction).
    entity_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    location_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("inventory_location.id", ondelete="RESTRICT"), nullable=False
    )
    on_hand: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
