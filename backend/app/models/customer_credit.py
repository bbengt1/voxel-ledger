"""ORM models for the customer-credit ledger (Phase 7.4, #112).

Two pieces:

* ``customer_credit_balance`` — projection-owned materialized row, one
  per customer with the current ``available_amount``. The service layer
  NEVER updates this directly; the projection in
  ``app/projections/customer_credit`` rebuilds it from the
  ``ar.CustomerCreditAccrued`` / ``ar.CustomerCreditApplied`` event
  stream.

* ``customer_credit_transaction`` — append-only ledger of credit
  movements. Each row is one accrual (positive delta) or application
  (negative delta to the balance, positive ``amount`` value with
  ``kind='application'``).

Per agents.md gotcha #1 the ``customer_credit_kind`` enum auto-creates
via the column dialect hook. Per gotcha #3 the ORM declares it with
``SAEnum(..., create_type=False)``.
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
    Text,
    func,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class CustomerCreditKind(enum.StrEnum):
    ACCRUAL = "accrual"
    APPLICATION = "application"
    EXPIRATION = "expiration"


CUSTOMER_CREDIT_KIND_VALUES: tuple[str, ...] = tuple(m.value for m in CustomerCreditKind)


CUSTOMER_CREDIT_KIND_ENUM = SAEnum(
    CustomerCreditKind,
    name="customer_credit_kind",
    values_callable=lambda enum_cls: [m.value for m in enum_cls],
    create_type=False,
)


class CustomerCreditBalance(Base):
    """Materialized per-customer credit balance.

    PROJECTION-OWNED. The service layer reads from this; it MUST NOT
    write to it directly. Writes happen only through the projection.
    """

    __tablename__ = "customer_credit_balance"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    customer_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("customer.id", ondelete="RESTRICT"), nullable=False, unique=True
    )
    available_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 6), nullable=False, default=Decimal("0"), server_default="0"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class CustomerCreditTransaction(Base):
    """Append-only ledger of credit movements.

    Each row is exactly one accrual, application, or (future) expiration.
    ``amount`` is always positive; the row's ``kind`` tells you whether
    it adds to or subtracts from the running balance.
    """

    __tablename__ = "customer_credit_transaction"
    __table_args__ = (
        Index("ix_customer_credit_transaction_customer_id", "customer_id"),
        Index("ix_customer_credit_transaction_created_at_id", "created_at", "id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    customer_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("customer.id", ondelete="RESTRICT"), nullable=False
    )
    kind: Mapped[CustomerCreditKind] = mapped_column(CUSTOMER_CREDIT_KIND_ENUM, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)

    source_invoice_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("invoice.id", ondelete="RESTRICT"), nullable=True
    )
    source_refund_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("refund.id", ondelete="RESTRICT"), nullable=True
    )
    source_payment_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("payment.id", ondelete="RESTRICT"), nullable=True
    )
    applied_to_invoice_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("invoice.id", ondelete="RESTRICT"), nullable=True
    )
    notes: Mapped[str | None] = mapped_column(Text(), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
