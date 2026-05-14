"""ORM model for the ``inventory_location`` table (Phase 3.1).

An inventory location is a physical or logical place stock lives:
workshop benches, finished-goods shelving, staging carts, customer-pickup
holds, consignment, and a ``virtual`` catch-all for adjustments that
don't correspond to a real bin. Future Phase 3.2 inventory transactions
will move stock between locations; this issue only owns the CRUD over
the locations themselves.

The partial unique constraint mirrors ``supply``: ``(code) WHERE
is_archived = false`` keeps the active code namespace clean while
allowing archived rows to share codes with fresh entries.

``kind`` is a PG enum (``inventory_location_kind``). On SQLite the same
``sa.Enum`` renders as a CHECK constraint, matching the ``rate_kind``
pattern from ``0009_supplies_rates``.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Index, String, Text, func, text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class InventoryLocationKind(enum.StrEnum):
    WORKSHOP = "workshop"
    FINISHED_GOODS = "finished_goods"
    STAGING = "staging"
    CUSTOMER_PICKUP = "customer_pickup"
    CONSIGNMENT = "consignment"
    VIRTUAL = "virtual"


# Stable PG enum name so Alembic migrations align across environments.
INVENTORY_LOCATION_KIND_ENUM = SAEnum(
    InventoryLocationKind,
    name="inventory_location_kind",
    values_callable=lambda enum_cls: [member.value for member in enum_cls],
)


class InventoryLocation(Base):
    __tablename__ = "inventory_location"
    __table_args__ = (
        # Partial unique index: only active rows enforce uniqueness on code.
        Index(
            "ux_inventory_location_code_active",
            "code",
            unique=True,
            sqlite_where=text("is_archived = 0"),
            postgresql_where=text("is_archived = false"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[str] = mapped_column(String(32), nullable=False)
    kind: Mapped[InventoryLocationKind] = mapped_column(
        INVENTORY_LOCATION_KIND_ENUM, nullable=False
    )
    description: Mapped[str | None] = mapped_column(Text(), nullable=True)

    is_archived: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
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
