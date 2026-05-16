"""ORM model for ``late_fee_policy`` (Phase 7.6, #114).

A late-fee policy is a per-customer (or global) rule used by the
daily late-fee worker to compute a debit-note amount against an
overdue invoice.

``customer_id`` is nullable: a row with ``customer_id IS NULL`` is the
global default. The worker picks the most-specific policy
(customer-specific > global) at evaluation time.

Per agents.md gotcha #1 the ``late_fee_kind`` enum is NOT
pre-created in the migration — ``op.create_table`` auto-creates the PG
type via the column's dialect hook. Per gotcha #3 the ORM declares it
with ``SAEnum(*VALUES, name=..., create_type=False)``.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    func,
    true,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class LateFeeKind(enum.StrEnum):
    PERCENT_OF_OUTSTANDING = "percent_of_outstanding"
    FLAT = "flat"
    COMPOUND_PERCENT = "compound_percent"


LATE_FEE_KIND_VALUES: tuple[str, ...] = tuple(m.value for m in LateFeeKind)


LATE_FEE_KIND_ENUM = SAEnum(
    LateFeeKind,
    name="late_fee_kind",
    values_callable=lambda enum_cls: [m.value for m in enum_cls],
    create_type=False,
)


class LateFeePolicy(Base):
    __tablename__ = "late_fee_policy"
    __table_args__ = (
        Index("ix_late_fee_policy_customer_id", "customer_id"),
        Index("ix_late_fee_policy_is_active", "is_active"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    # NULL = global default. Non-null = applies to that customer.
    customer_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("customer.id", ondelete="RESTRICT"), nullable=True
    )

    kind: Mapped[LateFeeKind] = mapped_column(LATE_FEE_KIND_ENUM, nullable=False)

    # Percent (e.g. 0.015 = 1.5 %) or flat dollar amount, depending on kind.
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)

    grace_period_days: Mapped[int] = mapped_column(
        Integer(), nullable=False, default=0, server_default="0"
    )
    apply_after_days: Mapped[int] = mapped_column(
        Integer(), nullable=False, default=30, server_default="30"
    )
    compound_interval_days: Mapped[int] = mapped_column(
        Integer(), nullable=False, default=30, server_default="30"
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean(), nullable=False, default=True, server_default=true()
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
