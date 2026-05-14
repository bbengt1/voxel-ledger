"""ORM model for the ``rate`` catalog table (Phase 2.2).

A rate is one of three kinds: ``labor`` (per-hour), ``machine``
(per-hour) or ``overhead`` (decimal percentage). ``value`` is stored as
Numeric(18, 6) regardless. ``is_default_for_kind`` is enforced
exclusive per-kind by a partial unique index in migration
``0009_supplies_rates``: at most one default per kind at the DB level.

``applies_to_printer_id`` is intentionally NOT a foreign key yet — the
``printer`` table lands in Phase 5. The column carries the eventual
intent; today it's an unconstrained UUID a frontend can populate via a
free-text input.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, Index, Numeric, String, func, text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class RateKind(enum.StrEnum):
    LABOR = "labor"
    MACHINE = "machine"
    OVERHEAD = "overhead"


# Stable PG enum name so Alembic migrations align across environments.
RATE_KIND_ENUM = SAEnum(
    RateKind,
    name="rate_kind",
    values_callable=lambda enum_cls: [member.value for member in enum_cls],
)


class Rate(Base):
    __tablename__ = "rate"
    __table_args__ = (
        # Partial unique index: at most one default rate per kind.
        # Backstops the service-layer ``set_default`` flip and is the
        # DB-level invariant exercised by
        # ``tests/test_rates_partial_unique_index.py``.
        Index(
            "ux_rate_default_per_kind",
            "kind",
            unique=True,
            sqlite_where=text("is_default_for_kind = 1"),
            postgresql_where=text("is_default_for_kind = true"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    kind: Mapped[RateKind] = mapped_column(RATE_KIND_ENUM, nullable=False)

    # Per-hour for labor/machine, decimal percentage (e.g. 0.15 == 15%)
    # for overhead. Validation lives in the service / schema layer.
    value: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)

    # Future Phase 5: foreign key to ``printer``. For now this is just a
    # UUID column carrying the eventual intent.
    applies_to_printer_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)

    is_default_for_kind: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )
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
