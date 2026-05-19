"""ORM models for bill payments + applications (Phase 8.3, #130).

The direct AP mirror of Phase 7.4 ``payment`` / ``payment_application``
— a ``bill_payment`` is a single outbound remittance to a vendor with
its own reference number (``BP-YYYY-NNNN``), an ``amount``, and a
state machine (``pending -> posted | cancelled | bounced``).

Unlike AR payments, AP has no ``marketplace`` method and no excess /
credit residue path — the customer-credit notion is one-way and lives
on the AR side only. Posting direction is reversed: Dr AP / Cr Bank.

Per agents.md gotcha #1 the ``bill_payment_method`` and
``bill_payment_state`` enums are NOT pre-created in the migration —
``op.create_table`` autocreates them. Per gotcha #3 the ORM declares
them with ``SAEnum(*VALUES, name=..., create_type=False, values_callable=...)``.
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
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class BillPaymentMethod(enum.StrEnum):
    CASH = "cash"
    CHECK = "check"
    ACH = "ach"
    WIRE = "wire"
    CARD = "card"
    OTHER = "other"


class BillPaymentState(enum.StrEnum):
    PENDING = "pending"
    POSTED = "posted"
    BOUNCED = "bounced"
    CANCELLED = "cancelled"


BILL_PAYMENT_METHOD_VALUES: tuple[str, ...] = tuple(m.value for m in BillPaymentMethod)
BILL_PAYMENT_STATE_VALUES: tuple[str, ...] = tuple(m.value for m in BillPaymentState)


BILL_PAYMENT_METHOD_ENUM = SAEnum(
    BillPaymentMethod,
    name="bill_payment_method",
    values_callable=lambda enum_cls: [m.value for m in enum_cls],
    create_type=False,
)

BILL_PAYMENT_STATE_ENUM = SAEnum(
    BillPaymentState,
    name="bill_payment_state",
    values_callable=lambda enum_cls: [m.value for m in enum_cls],
    create_type=False,
)


class BillPayment(Base):
    __tablename__ = "bill_payment"
    __table_args__ = (
        Index("ix_bill_payment_state", "state"),
        Index("ix_bill_payment_vendor_id", "vendor_id"),
        Index("ix_bill_payment_occurred_at", "occurred_at"),
        Index("ix_bill_payment_created_at_id", "created_at", "id"),
        # Partial unique: ``(vendor_id, reference_number)`` only when
        # ``reference_number IS NOT NULL`` (NULL references allowed).
        Index(
            "uq_bill_payment_vendor_reference",
            "vendor_id",
            "reference_number",
            unique=True,
            postgresql_where=text("reference_number IS NOT NULL"),
            sqlite_where=text("reference_number IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    payment_number: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)

    vendor_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("vendor.id", ondelete="RESTRICT"), nullable=False
    )

    method: Mapped[BillPaymentMethod] = mapped_column(BILL_PAYMENT_METHOD_ENUM, nullable=False)

    amount: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)

    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # Free-form operator reference — check #, wire id, etc. Bounded by
    # column length and NEVER surfaced in audit excerpts.
    reference_number: Mapped[str | None] = mapped_column(String(64), nullable=True)

    notes: Mapped[str | None] = mapped_column(Text(), nullable=True)

    state: Mapped[BillPaymentState] = mapped_column(
        BILL_PAYMENT_STATE_ENUM,
        nullable=False,
        default=BillPaymentState.PENDING,
        server_default="pending",
    )

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

    applications: Mapped[list[BillPaymentApplication]] = relationship(
        "BillPaymentApplication",
        back_populates="bill_payment",
        cascade="all, delete-orphan",
    )


class BillPaymentApplication(Base):
    __tablename__ = "bill_payment_application"
    __table_args__ = (
        UniqueConstraint(
            "bill_payment_id", "bill_id", name="uq_bill_payment_application_payment_bill"
        ),
        Index("ix_bill_payment_application_bill_payment_id", "bill_payment_id"),
        Index("ix_bill_payment_application_bill_id", "bill_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    bill_payment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("bill_payment.id", ondelete="CASCADE"), nullable=False
    )
    bill_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("bill.id", ondelete="RESTRICT"), nullable=False
    )
    amount_applied: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)

    # Phase 9.7 (#159) — per-application withholding stamps. ``withholding_amount``
    # is the portion of ``amount_applied`` that was Cr'd to the
    # withholding-liability account instead of bank. Zero means "no
    # withholding applied".
    withholding_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 6), nullable=False, default=Decimal("0"), server_default=text("0")
    )
    withholding_profile_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("withholding_profile.id", ondelete="SET NULL"), nullable=True
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

    bill_payment: Mapped[BillPayment] = relationship("BillPayment", back_populates="applications")
