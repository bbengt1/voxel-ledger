"""ORM model for ``withholding_profile`` (Phase 9.7, #159).

A withholding profile encodes a tax-authority withholding rate (e.g.
US 1099-NEC backup-withholding) and the liability account that
collects the withheld amount. Bill-payment apply consults the resolved
profile to split the Cr side of the JE: ``Cr Bank = amt - withheld``
and ``Cr Liability = withheld``.

CRITICAL PII RULE
-----------------
``notes`` is operator free-text and MUST NEVER be whitelisted into the
audit excerpt. See ``app/projections/audit/excerpts.py``.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    func,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class WithholdingProfile(Base):
    __tablename__ = "withholding_profile"
    __table_args__ = (
        CheckConstraint("rate >= 0 AND rate <= 1", name="ck_withholding_profile_rate_range"),
        Index("ix_withholding_profile_is_active", "is_active"),
        Index("ix_withholding_profile_jurisdiction", "jurisdiction"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    jurisdiction: Mapped[str] = mapped_column(String(64), nullable=False)

    rate: Mapped[Decimal] = mapped_column(Numeric(7, 5), nullable=False)

    liability_account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("account.id", ondelete="RESTRICT"), nullable=False
    )

    threshold_per_year: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    form_kind: Mapped[str | None] = mapped_column(String(32), nullable=True)

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


__all__ = ["WithholdingProfile"]
