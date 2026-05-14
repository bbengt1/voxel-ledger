"""ORM model for the ``inventory_transaction`` table (Phase 3.2, #51).

One row per physical movement of stock — production output, sale,
adjustment, return, waste, receipt, or one half of a transfer. The
ledger is **append-only**: the migration installs an immutability
trigger on Postgres that raises on UPDATE/DELETE. SQLite (used by unit
tests) skips the trigger; the immutability invariant is exercised by a
PG-only integration test instead.

``entity_kind`` + ``entity_id`` is a polymorphic reference to one of the
catalog tables (``material``, ``supply``, ``product``). Integrity is
enforced in ``app.services.inventory_transactions`` — there is no FK
because the target table varies. This mirrors the ``component_kind`` /
``component_id`` pattern from ``product_bom_item`` (#40).

``kind`` and ``entity_kind`` are PG ENUMs created by the migration. The
ORM declares them with ``SAEnum(*VALUES, name=..., create_type=False)``
so SQLAlchemy emits the right cast on comparisons (a plain ``String``
column made every WHERE clause fail on Postgres with "operator does not
exist: <enum_type> = character varying" — see #55).

``quantity`` is **signed**. The service computes the sign from ``kind``:
positive for stock arriving (``production_in``, ``return_in``,
``receipt``, ``transfer_in``), negative for stock leaving (``sale_out``,
``waste``, ``transfer_out``). ``adjustment`` accepts a signed magnitude
verbatim.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    Text,
    func,
    text,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base

# Allowed values for the kind enum. Mirrored in the Alembic migration
# (PG ENUM ``inventory_transaction_kind`` / SQLite CHECK constraint).
KIND_PRODUCTION_IN = "production_in"
KIND_SALE_OUT = "sale_out"
KIND_ADJUSTMENT = "adjustment"
KIND_RETURN_IN = "return_in"
KIND_WASTE = "waste"
KIND_RECEIPT = "receipt"
KIND_TRANSFER_IN = "transfer_in"
KIND_TRANSFER_OUT = "transfer_out"
INVENTORY_TRANSACTION_KIND_VALUES: tuple[str, ...] = (
    KIND_PRODUCTION_IN,
    KIND_SALE_OUT,
    KIND_ADJUSTMENT,
    KIND_RETURN_IN,
    KIND_WASTE,
    KIND_RECEIPT,
    KIND_TRANSFER_IN,
    KIND_TRANSFER_OUT,
)

# Per-kind sign of ``quantity``. ``adjustment`` is ``None`` — caller
# supplies the sign.
POSITIVE_KINDS: frozenset[str] = frozenset(
    {KIND_PRODUCTION_IN, KIND_RETURN_IN, KIND_RECEIPT, KIND_TRANSFER_IN}
)
NEGATIVE_KINDS: frozenset[str] = frozenset({KIND_SALE_OUT, KIND_WASTE, KIND_TRANSFER_OUT})

# Polymorphic entity_kind enum.
ENTITY_KIND_MATERIAL = "material"
ENTITY_KIND_SUPPLY = "supply"
ENTITY_KIND_PRODUCT = "product"
INVENTORY_ENTITY_KIND_VALUES: tuple[str, ...] = (
    ENTITY_KIND_MATERIAL,
    ENTITY_KIND_SUPPLY,
    ENTITY_KIND_PRODUCT,
)


INVENTORY_TRANSACTION_KIND_ENUM = SAEnum(
    *INVENTORY_TRANSACTION_KIND_VALUES,
    name="inventory_transaction_kind",
    native_enum=True,
    create_type=False,
)
INVENTORY_ENTITY_KIND_ENUM = SAEnum(
    *INVENTORY_ENTITY_KIND_VALUES,
    name="inventory_entity_kind",
    native_enum=True,
    create_type=False,
)


class InventoryTransaction(Base):
    __tablename__ = "inventory_transaction"
    __table_args__ = (
        # Hot path for "what's the current on-hand of (entity, location)"
        # — Phase 3.3 will sum signed quantities over this index.
        Index(
            "ix_inventory_tx_entity_location_occurred",
            "entity_kind",
            "entity_id",
            "location_id",
            "occurred_at",
        ),
        Index(
            "ix_inventory_tx_location_occurred",
            "location_id",
            "occurred_at",
        ),
        Index(
            "ix_inventory_tx_kind_occurred",
            "kind",
            "occurred_at",
        ),
        # Partial index — only matters when transfer_pair_id is set.
        Index(
            "ix_inventory_tx_transfer_pair",
            "transfer_pair_id",
            sqlite_where=text("transfer_pair_id IS NOT NULL"),
            postgresql_where=text("transfer_pair_id IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    kind: Mapped[str] = mapped_column(INVENTORY_TRANSACTION_KIND_ENUM, nullable=False)
    entity_kind: Mapped[str] = mapped_column(INVENTORY_ENTITY_KIND_ENUM, nullable=False)
    # Polymorphic reference — no FK; integrity enforced in the service.
    entity_id: Mapped[uuid.UUID] = mapped_column(nullable=False)

    location_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("inventory_location.id"), nullable=False
    )

    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    unit_cost_at_transaction: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    total_cost_at_transaction: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)

    transfer_pair_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    # Phase 5 / 6 hooks. No FK yet — those tables don't exist.
    linked_job_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    linked_sale_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)

    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )
    reason: Mapped[str | None] = mapped_column(Text(), nullable=True)
