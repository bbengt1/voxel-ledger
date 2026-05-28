"""ORM models for deposit slips (Parity #235).

A deposit slip groups N customer payments that landed in the
undeposited-funds clearing account into one bank deposit — matching
how the bank statement reports it (one consolidated credit on the
statement, not N separate ones).
"""

from __future__ import annotations

import enum
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class DepositSlipState(enum.StrEnum):
    DRAFT = "draft"
    DEPOSITED = "deposited"
    RECONCILED = "reconciled"


DEPOSIT_SLIP_STATE_VALUES: tuple[str, ...] = tuple(m.value for m in DepositSlipState)


DEPOSIT_SLIP_STATE_ENUM = SAEnum(
    DepositSlipState,
    name="deposit_slip_state",
    values_callable=lambda enum_cls: [m.value for m in enum_cls],
    create_type=False,
)


class DepositSlip(Base):
    __tablename__ = "deposit_slip"
    __table_args__ = (Index("ix_deposit_slip_bank_state", "bank_account_id", "state"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    slip_number: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    bank_account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("account.id", ondelete="RESTRICT"), nullable=False
    )
    deposit_date: Mapped[date] = mapped_column(Date(), nullable=False)
    total_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 6), nullable=False, default=Decimal("0"), server_default="0"
    )
    state: Mapped[DepositSlipState] = mapped_column(
        DEPOSIT_SLIP_STATE_ENUM,
        nullable=False,
        default=DepositSlipState.DRAFT,
        server_default="draft",
    )
    posting_journal_entry_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("journal_entry.id", ondelete="SET NULL"), nullable=True
    )
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
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


class DepositSlipItem(Base):
    __tablename__ = "deposit_slip_item"
    __table_args__ = (
        UniqueConstraint("payment_id", name="uq_deposit_slip_item_payment"),
        Index("ix_deposit_slip_item_slip", "deposit_slip_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    deposit_slip_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("deposit_slip.id", ondelete="CASCADE"), nullable=False
    )
    payment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("payment.id", ondelete="RESTRICT"), nullable=False
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)


__all__ = [
    "DEPOSIT_SLIP_STATE_VALUES",
    "DepositSlip",
    "DepositSlipItem",
    "DepositSlipState",
]
