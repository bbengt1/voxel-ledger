"""ORM model for ``late_fee_policy`` (Phase 7.6, #114).

A policy describes how to compute late fees on overdue invoices for a
specific customer (``customer_id`` set) or globally (``customer_id``
null). The Phase 7.6 worker resolves the most-specific active policy
per overdue invoice (per-customer beats global) and emits a debit note.

Per agents.md gotcha #1 the ``late_fee_kind`` enum auto-creates via the
column dialect hook in the 0038 migration. Per gotcha #3 the ORM
declares it with ``SAEnum(..., create_type=False)`` so the type is
referenced, not re-created, at runtime.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
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
        CheckConstraint("amount >= 0", name="ck_late_fee_policy_amount_nonneg"),
        CheckConstraint("grace_period_days >= 0", name="ck_late_fee_policy_grace_nonneg"),
        CheckConstraint("apply_after_days >= 0", name="ck_late_fee_policy_apply_after_nonneg"),
        CheckConstraint(
            "compound_interval_days >= 1",
            name="ck_late_fee_policy_compound_interval_positive",
        ),
        Index("ix_late_fee_policy_customer_id", "customer_id"),
        Index("ix_late_fee_policy_is_active", "is_active"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    customer_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("customer.id", ondelete="CASCADE"), nullable=True
    )

    kind: Mapped[LateFeeKind] = mapped_column(LATE_FEE_KIND_ENUM, nullable=False)
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
        Boolean(), nullable=False, default=True, server_default="true"
    )

    notes: Mapped[str | None] = mapped_column(Text(), nullable=True)

    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("user.id", ondelete="RESTRICT"), nullable=True
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
