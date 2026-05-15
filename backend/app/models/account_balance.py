"""ORM model for the ``account_balance`` read model (Phase 4.2, #65).

One row per account. Maintained by the ``account_balance`` projection
which subscribes to ``accounting.JournalEntryPosted``. The net balance
is computed at read time from ``total_debits`` and ``total_credits``
according to the account's natural sign (asset/expense → debit;
liability/equity/revenue → credit).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Numeric, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class AccountBalance(Base):
    __tablename__ = "account_balance"

    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("account.id", ondelete="RESTRICT"), primary_key=True
    )
    total_debits: Mapped[Decimal] = mapped_column(
        Numeric(18, 6), nullable=False, server_default="0"
    )
    total_credits: Mapped[Decimal] = mapped_column(
        Numeric(18, 6), nullable=False, server_default="0"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
