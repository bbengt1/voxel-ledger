"""ORM models for payments + payment applications (Phase 7.4, #112).

A ``payment`` is a single customer remittance — cash, check, ACH, wire,
card, marketplace clearing, or "other". It has its own reference number
(``PMT-YYYY-NNNN``), an ``amount``, and a state machine
(``pending -> applied | cancelled | bounced``).

A ``payment_application`` row links one payment to one invoice with a
``Numeric(18, 6)`` portion applied. The sum of applications for a
payment must be ≤ payment.amount; the residue (if any) becomes a
``customer_credit_transaction`` accrual when the operator opts in to
``apply_excess_to_credit``.

Per agents.md gotcha #1 the ``payment_method`` and ``payment_state``
enums are NOT pre-created in the migration — ``op.create_table``
autocreates them via the columns' dialect hook. Per gotcha #3 the ORM
declares them with ``SAEnum(*VALUES, name=..., create_type=False)``.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class PaymentMethod(enum.StrEnum):
    CASH = "cash"
    CHECK = "check"
    ACH = "ach"
    WIRE = "wire"
    CARD = "card"
    MARKETPLACE = "marketplace"
    OTHER = "other"


class PaymentState(enum.StrEnum):
    PENDING = "pending"
    APPLIED = "applied"
    CANCELLED = "cancelled"
    BOUNCED = "bounced"


PAYMENT_METHOD_VALUES: tuple[str, ...] = tuple(m.value for m in PaymentMethod)
PAYMENT_STATE_VALUES: tuple[str, ...] = tuple(m.value for m in PaymentState)


PAYMENT_METHOD_ENUM = SAEnum(
    PaymentMethod,
    name="payment_method",
    values_callable=lambda enum_cls: [m.value for m in enum_cls],
    create_type=False,
)

PAYMENT_STATE_ENUM = SAEnum(
    PaymentState,
    name="payment_state",
    values_callable=lambda enum_cls: [m.value for m in enum_cls],
    create_type=False,
)


class Payment(Base):
    __tablename__ = "payment"
    __table_args__ = (
        Index("ix_payment_state", "state"),
        Index("ix_payment_customer_id", "customer_id"),
        Index("ix_payment_received_at", "received_at"),
        Index("ix_payment_created_at_id", "created_at", "id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    payment_number: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)

    customer_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("customer.id", ondelete="RESTRICT"), nullable=False
    )

    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    method: Mapped[PaymentMethod] = mapped_column(PAYMENT_METHOD_ENUM, nullable=False)

    # Free-form operator reference — check number, last-4 of card, marketplace
    # transaction id, etc. Bounded by column length; NEVER appears in
    # log lines or audit excerpts. See excerpts whitelist.
    reference: Mapped[str | None] = mapped_column(String(128), nullable=True)

    amount: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)

    state: Mapped[PaymentState] = mapped_column(
        PAYMENT_STATE_ENUM,
        nullable=False,
        default=PaymentState.PENDING,
        server_default="pending",
    )

    notes: Mapped[str | None] = mapped_column(Text(), nullable=True)

    posting_journal_entry_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("journal_entry.id", ondelete="RESTRICT"), nullable=True
    )

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

    applications: Mapped[list[PaymentApplication]] = relationship(
        "PaymentApplication",
        back_populates="payment",
        cascade="all, delete-orphan",
    )


class PaymentApplication(Base):
    __tablename__ = "payment_application"
    __table_args__ = (
        Index("ix_payment_application_payment_id", "payment_id"),
        Index("ix_payment_application_invoice_id", "invoice_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    payment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("payment.id", ondelete="CASCADE"), nullable=False
    )
    invoice_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("invoice.id", ondelete="RESTRICT"), nullable=False
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    applied_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    payment: Mapped[Payment] = relationship("Payment", back_populates="applications")
