"""ORM models for the ``bank_reconciliation`` aggregate (Phase 8.11, #138).

The reconciliation aggregate captures the operator's tick-mark workflow:

* :class:`BankReconciliation` — header row pinning an account + period +
  the statement's ending balance the operator typed in.
* :class:`BankReconciliationItem` — the membership of a specific
  ``bank_transaction`` row in a reconciliation, along with whether the
  operator has ticked it cleared.

The ``bank_reconciliation_state`` PG enum is auto-created by migration
0049 (gotcha #1). Per gotcha #3 the ORM declares it with
``SAEnum(..., create_type=False)``.
"""

from __future__ import annotations

import enum
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    Text,
    UniqueConstraint,
    false,
    func,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class BankReconciliationState(enum.StrEnum):
    IN_PROGRESS = "in_progress"
    BALANCED = "balanced"
    FINALIZED = "finalized"


BANK_RECONCILIATION_STATE_VALUES: tuple[str, ...] = tuple(m.value for m in BankReconciliationState)


BANK_RECONCILIATION_STATE_ENUM = SAEnum(
    BankReconciliationState,
    name="bank_reconciliation_state",
    values_callable=lambda enum_cls: [m.value for m in enum_cls],
    create_type=False,
)


_SA_FALSE = false()


class BankReconciliation(Base):
    __tablename__ = "bank_reconciliation"
    __table_args__ = (
        Index("ix_bank_reconciliation_account_state", "account_id", "state"),
        Index("ix_bank_reconciliation_period_end", "period_end"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("account.id", ondelete="RESTRICT"), nullable=False
    )
    period_start: Mapped[date] = mapped_column(Date(), nullable=False)
    period_end: Mapped[date] = mapped_column(Date(), nullable=False)
    statement_ending_balance: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    book_ending_balance: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    difference: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    state: Mapped[BankReconciliationState] = mapped_column(
        BANK_RECONCILIATION_STATE_ENUM,
        nullable=False,
        default=BankReconciliationState.IN_PROGRESS,
        server_default="in_progress",
    )
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finalized_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("user.id", ondelete="RESTRICT"), nullable=True
    )
    notes: Mapped[str | None] = mapped_column(Text(), nullable=True)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("user.id", ondelete="RESTRICT"), nullable=False
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


class BankReconciliationItem(Base):
    __tablename__ = "bank_reconciliation_item"
    __table_args__ = (
        UniqueConstraint(
            "reconciliation_id",
            "bank_transaction_id",
            name="uq_bank_reconciliation_item_recon_tx",
        ),
        Index(
            "ix_bank_reconciliation_item_reconciliation_id",
            "reconciliation_id",
        ),
        Index(
            "ix_bank_reconciliation_item_bank_transaction_id",
            "bank_transaction_id",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    reconciliation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("bank_reconciliation.id", ondelete="CASCADE"), nullable=False
    )
    bank_transaction_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("bank_transaction.id", ondelete="RESTRICT"), nullable=False
    )
    is_cleared: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=_SA_FALSE
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
