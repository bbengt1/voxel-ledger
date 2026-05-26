"""ORM model for the ``printer`` table (Phase 5.1).

A printer is a physical 3D-printing machine. The ``slug`` partial unique
index mirrors ``inventory_location`` / ``supply``: only active rows
enforce uniqueness, so archived rows can share slugs with new entries.

``printer_type`` is a PG enum (``printer_type``). On SQLite the same
``SAEnum`` renders as ``VARCHAR + CHECK``.

The ``moonraker_api_key`` column is an opaque secret. It is NEVER
serialized into a response, event payload, or audit excerpt — the
service layer substitutes the sentinel ``"***"`` for it everywhere.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from decimal import Decimal

from sqlalchemy import Boolean, DateTime, Index, Integer, Numeric, String, Text, func, text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class PrinterType(enum.StrEnum):
    PRUSA_MK4 = "prusa_mk4"
    PRUSA_MK3S = "prusa_mk3s"
    BAMBU_X1C = "bambu_x1c"
    BAMBU_A1 = "bambu_a1"
    VORON_V2_4 = "voron_v2_4"
    OTHER = "other"


PRINTER_TYPE_VALUES: tuple[str, ...] = tuple(m.value for m in PrinterType)


PRINTER_TYPE_ENUM = SAEnum(
    PrinterType,
    name="printer_type",
    values_callable=lambda enum_cls: [member.value for member in enum_cls],
)


class Printer(Base):
    __tablename__ = "printer"
    __table_args__ = (
        Index(
            "ux_printer_slug_active",
            "slug",
            unique=True,
            sqlite_where=text("is_archived = 0"),
            postgresql_where=text("is_archived = false"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(64), nullable=False)
    printer_type: Mapped[PrinterType] = mapped_column(PRINTER_TYPE_ENUM, nullable=False)

    moonraker_url: Mapped[str | None] = mapped_column(Text(), nullable=True)
    # SECRET — never echoed to clients/events/excerpts. Service layer
    # replaces the value with the sentinel "***" everywhere it surfaces.
    moonraker_api_key: Mapped[str | None] = mapped_column(Text(), nullable=True)

    power_draw_watts: Mapped[int | None] = mapped_column(Integer(), nullable=True)

    # Cost-engine inputs (#249). All optional. When the full set is
    # populated (purchase_price, salvage_value, lifespan_years,
    # annual_print_hours) the cost engine derives a per-hour
    # depreciation rate; preheat_minutes + preheat_power_watts add a
    # one-shot preheat electricity cost per print run.
    purchase_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    salvage_value: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    lifespan_years: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    annual_print_hours: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    preheat_minutes: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    preheat_power_watts: Mapped[int | None] = mapped_column(Integer(), nullable=True)

    notes: Mapped[str | None] = mapped_column(Text(), nullable=True)

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
