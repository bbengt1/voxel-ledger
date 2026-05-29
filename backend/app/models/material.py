"""ORM model for the ``material`` catalog table (Phase 2.1, 3.3).

A material is one physical filament/resin SKU. ``current_cost_per_gram``
is a read-side cache maintained by the ``material_cost`` projection from
the ``inventory.MaterialReceived`` event stream — never mutated directly
by service code.

Phase 3.3 (#52) refactor: ``on_hand_grams`` is GONE. On-hand quantities
now live in ``inventory_on_hand``, summed per ``(entity_kind, entity_id,
location_id)`` triple. ``low_stock_threshold_grams`` is a new editable
column; NULL means no alert is configured.

The unique constraint on ``(name, brand, color) where is_archived = false``
keeps the active catalog free of dupes while allowing archived rows to
coexist with a fresh entry of the same name.

``custom_fields`` is intentionally out of scope here (lands in #2.5).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Boolean, CheckConstraint, DateTime, Numeric, String, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.core.db import Base

_CUSTOM_FIELDS_TYPE = JSON().with_variant(JSONB(), "postgresql")


class Material(Base):
    __tablename__ = "material"
    __table_args__ = (
        CheckConstraint(
            "spool_weight_grams >= 0",
            name="ck_material_spool_weight_grams_non_negative",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    brand: Mapped[str | None] = mapped_column(String(255), nullable=True)
    material_type: Mapped[str] = mapped_column(String(64), nullable=False)
    color: Mapped[str | None] = mapped_column(String(64), nullable=True)

    density_g_per_cm3: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)

    # Spool-centric inventory model: every receipt is entered as
    # (spools * spool_weight) + extra_grams. ``spool_weight_grams = 0``
    # is permitted at the DB layer purely for backwards compatibility
    # with rows created before this feature shipped — the API rejects
    # creating new materials with 0, and rejects receipts against a
    # material whose spool weight is 0. Backfill via the UI.
    spool_weight_grams: Mapped[Decimal] = mapped_column(
        Numeric(18, 6),
        nullable=False,
        default=Decimal("0"),
        server_default=text("0"),
    )

    # Read-side caches. Recomputed by the ``material_cost`` projection;
    # never written by service code. Defaults are zero so a freshly
    # created material has well-defined numbers even before the first
    # receipt.
    current_cost_per_gram: Mapped[Decimal] = mapped_column(
        Numeric(18, 6),
        nullable=False,
        default=Decimal("0"),
        server_default="0",
    )

    # Phase 3.3: low-stock alert threshold. NULL = no alert configured.
    low_stock_threshold_grams: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)

    is_archived: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )

    # Schema-on-read custom-field payload (Phase 2.5). Validated against
    # the active ``custom_field`` definitions at the service boundary;
    # unknown keys are tolerated for replay safety.
    custom_fields: Mapped[dict[str, Any]] = mapped_column(
        _CUSTOM_FIELDS_TYPE,
        nullable=False,
        default=dict,
        server_default=text("'{}'"),
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
