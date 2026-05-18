"""ORM models for ``tax_profile`` + ``tax_rate`` (Phase 9.5, #157).

Replaces the flat ``tax_amount`` on invoices/bills (which still exists
but is now a derived per-line aggregate). A tax profile bundles one or
more ordered rates; each rate is either a flat percentage of the
subtotal or a compound rate applied on subtotal + previous-rate-amounts.

``is_reverse_charge`` turns the entire profile into a memo (no Cr to a
liability is posted; replay can still compute the buyer obligation from
the event payload's ``reverse_charge_tax`` field).
"""

from __future__ import annotations

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
    String,
    Text,
    UniqueConstraint,
    false,
    func,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class TaxProfile(Base):
    __tablename__ = "tax_profile"
    __table_args__ = (
        Index("ix_tax_profile_is_active", "is_active"),
        Index("ix_tax_profile_jurisdiction", "jurisdiction"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    jurisdiction: Mapped[str] = mapped_column(String(64), nullable=False)

    is_reverse_charge: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
    notes: Mapped[str | None] = mapped_column(Text(), nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=true()
    )

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

    rates: Mapped[list[TaxRate]] = relationship(
        "TaxRate",
        back_populates="profile",
        cascade="all, delete-orphan",
        order_by="TaxRate.ordinal",
    )


class TaxRate(Base):
    __tablename__ = "tax_rate"
    __table_args__ = (
        UniqueConstraint("profile_id", "ordinal", name="uq_tax_rate_profile_ordinal"),
        Index("ix_tax_rate_profile_id", "profile_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tax_profile.id", ondelete="CASCADE"), nullable=False
    )
    ordinal: Mapped[int] = mapped_column(Integer(), nullable=False)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    rate: Mapped[Decimal] = mapped_column(Numeric(7, 5), nullable=False)

    liability_account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("account.id", ondelete="RESTRICT"), nullable=False
    )

    compound_on_previous: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
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

    profile: Mapped[TaxProfile] = relationship("TaxProfile", back_populates="rates")
