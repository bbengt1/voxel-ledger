"""ORM model for the ``budget`` table (Phase 4.5, #68).

A budgeted amount per ``(account, division, period)`` slot. ``division_id``
is nullable — a row with ``division_id IS NULL`` is the "catch-all" budget
for the account in that period, not attributable to any specific division.

Uniqueness contract
-------------------
PG 15+: the migration installs ``UNIQUE (account_id, division_id, period_id)
NULLS NOT DISTINCT`` so the catch-all row is genuinely unique per
``(account, period)``. SQLite has no NULLS-NOT-DISTINCT support, so the
service-layer check is the authoritative guard there; the migration
declares a plain ``UNIQUE`` constraint as a partial fallback for
non-null trios.

``amount`` is required positive (CHECK ``amount >= 0``). Currency-free
Numeric(18, 6) to match the journal-line precision.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Budget(Base):
    __tablename__ = "budget"
    __table_args__ = (
        CheckConstraint("amount >= 0", name="ck_budget_amount_nonneg"),
        # SQLite-friendly UNIQUE; PG migration replaces this with a
        # NULLS NOT DISTINCT variant via the migration.
        UniqueConstraint(
            "account_id",
            "division_id",
            "period_id",
            name="ux_budget_account_division_period",
        ),
        Index("ix_budget_period_account", "period_id", "account_id"),
        Index("ix_budget_division", "division_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("account.id", ondelete="RESTRICT"), nullable=False
    )
    division_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("division.id", ondelete="RESTRICT"), nullable=True
    )
    period_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("accounting_period.id", ondelete="RESTRICT"), nullable=False
    )

    amount: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
