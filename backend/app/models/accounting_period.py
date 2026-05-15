"""ORM model for the ``accounting_period`` table (Phase 4.3, #66).

A period is an inclusive date range (``[start_date, end_date]``) with a
small open/closed/locked state machine. Periods may not overlap; the
service-layer check is the primary defense and is mirrored on PG via a
GiST exclusion constraint installed by the migration.

``state`` is a PG ENUM (``accounting_period_state``) declared with
``SAEnum(..., create_type=False)`` so Alembic owns the lifecycle — same
pattern as ``account.type`` / ``inventory_location.kind``.

Mutation is always through the service; the model itself carries no
business rules.
"""

from __future__ import annotations

import enum
import uuid
from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Index, String, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class AccountingPeriodState(enum.StrEnum):
    OPEN = "open"
    CLOSED = "closed"
    LOCKED = "locked"


ACCOUNTING_PERIOD_STATE_VALUES: tuple[str, ...] = tuple(
    member.value for member in AccountingPeriodState
)


# Stable PG enum name. ``create_type=False`` so the migration owns
# creation; ORM merely references the existing type at runtime.
ACCOUNTING_PERIOD_STATE_ENUM = SAEnum(
    *ACCOUNTING_PERIOD_STATE_VALUES,
    name="accounting_period_state",
    create_type=False,
)


class AccountingPeriod(Base):
    __tablename__ = "accounting_period"
    __table_args__ = (
        CheckConstraint(
            "end_date >= start_date",
            name="ck_accounting_period_end_after_start",
        ),
        Index("ix_accounting_period_start_date", "start_date"),
        Index("ix_accounting_period_end_date", "end_date"),
        Index(
            "ix_accounting_period_state_end_date",
            "state",
            "end_date",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    name: Mapped[str] = mapped_column(String(64), nullable=False)
    start_date: Mapped[date] = mapped_column(Date(), nullable=False)
    end_date: Mapped[date] = mapped_column(Date(), nullable=False)
    state: Mapped[str] = mapped_column(
        ACCOUNTING_PERIOD_STATE_ENUM,
        nullable=False,
        default=AccountingPeriodState.OPEN.value,
        server_default=AccountingPeriodState.OPEN.value,
    )

    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    locked_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
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
