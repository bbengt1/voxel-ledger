"""ORM model for the ``part`` catalog table (assembly-line epic #267, Phase 1).

A part is a *printed unit* — the thing a job produces — made of materials.
Products are assembled from parts + supplies (later phases). A part can
belong to many products (many-to-many, wired in Phase 3).

The **print recipe** lives on the part (epic decision #1): print time,
setup time, parts-per-run, the per-material gram usage, and the eligible
printers. ``print_grams_by_material`` mirrors ``plate.print_grams_by_material``
(a JSON dict of ``material_id -> grams`` as decimal strings) so the Phase 7
migration from plates is a straight lift and the Phase 2 cost rollup can
read it directly.

``unit_cost_cached`` is reserved for the Phase 2 cost rollup — created
here as nullable; neither read nor written in Phase 1.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Boolean, DateTime, Integer, Numeric, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.core.db import Base

_JSON_TYPE = JSON().with_variant(JSONB(), "postgresql")


class Part(Base):
    __tablename__ = "part"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    sku: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text(), nullable=True)

    # --- Print recipe (epic #267 decision #1) ---
    print_minutes: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    setup_minutes: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    # Finished parts produced per print run (> 0).
    parts_per_run: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    # ``{material_id_str: grams_str}`` — same shape as ``plate``.
    print_grams_by_material: Mapped[dict[str, Any]] = mapped_column(
        _JSON_TYPE, nullable=False, default=dict, server_default=text("'{}'")
    )
    # List of eligible/assigned printer ids (uuid strings).
    assigned_printer_ids: Mapped[list[Any]] = mapped_column(
        _JSON_TYPE, nullable=False, default=list, server_default=text("'[]'")
    )

    # Reserved for the Phase 2 cost rollup; never set/read in Phase 1.
    unit_cost_cached: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)

    is_archived: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )

    custom_fields: Mapped[dict[str, Any]] = mapped_column(
        _JSON_TYPE, nullable=False, default=dict, server_default=text("'{}'")
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
