"""ORM model for ``tax_remittance`` (Phase 9.6, #158).

A row per remittance payment to a revenue authority for a given tax
profile + period window. The service layer posts a balanced JE (Dr the
profile's per-rate liability accounts / Cr bank) in the same DB
transaction as the row insert; ``posting_journal_entry_id`` is stamped
once that JE exists.

Per agents.md gotcha #1 the two enums (``tax_remittance_state``,
``tax_remittance_method``) are NOT pre-created in the migration;
``op.create_table`` auto-creates the PG types via the column dialect
hook. Per gotcha #3 the ORM declares them with
``SAEnum(..., create_type=False, values_callable=...)``.
"""

from __future__ import annotations

import enum
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class TaxRemittanceState(enum.StrEnum):
    RECORDED = "recorded"
    CANCELLED = "cancelled"


class TaxRemittanceMethod(enum.StrEnum):
    ACH = "ach"
    CHECK = "check"
    WIRE = "wire"
    OTHER = "other"


TAX_REMITTANCE_STATE_VALUES: tuple[str, ...] = tuple(m.value for m in TaxRemittanceState)
TAX_REMITTANCE_METHOD_VALUES: tuple[str, ...] = tuple(m.value for m in TaxRemittanceMethod)


TAX_REMITTANCE_STATE_ENUM = SAEnum(
    TaxRemittanceState,
    name="tax_remittance_state",
    values_callable=lambda enum_cls: [m.value for m in enum_cls],
    create_type=False,
)
TAX_REMITTANCE_METHOD_ENUM = SAEnum(
    TaxRemittanceMethod,
    name="tax_remittance_method",
    values_callable=lambda enum_cls: [m.value for m in enum_cls],
    create_type=False,
)


class TaxRemittance(Base):
    __tablename__ = "tax_remittance"
    __table_args__ = (
        CheckConstraint("amount_paid > 0", name="ck_tax_remittance_amount_positive"),
        CheckConstraint("period_end >= period_start", name="ck_tax_remittance_period_range"),
        Index("ix_tax_remittance_profile_id", "profile_id"),
        Index("ix_tax_remittance_state", "state"),
        Index("ix_tax_remittance_paid_on", "paid_on"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    remittance_number: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)

    profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tax_profile.id", ondelete="RESTRICT"), nullable=False
    )

    period_start: Mapped[date] = mapped_column(Date(), nullable=False)
    period_end: Mapped[date] = mapped_column(Date(), nullable=False)

    amount_paid: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    paid_on: Mapped[date] = mapped_column(Date(), nullable=False)

    method: Mapped[TaxRemittanceMethod] = mapped_column(TAX_REMITTANCE_METHOD_ENUM, nullable=False)

    reference_number: Mapped[str | None] = mapped_column(String(64), nullable=True)

    bank_account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("account.id", ondelete="RESTRICT"), nullable=False
    )

    state: Mapped[TaxRemittanceState] = mapped_column(
        TAX_REMITTANCE_STATE_ENUM,
        nullable=False,
        default=TaxRemittanceState.RECORDED,
        server_default="recorded",
    )

    posting_journal_entry_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("journal_entry.id", ondelete="SET NULL"), nullable=True
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
