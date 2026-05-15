"""ORM model for the ``journal_line`` table (Phase 4.2, #65).

One row per debit-or-credit posting. The DB CHECK enforces the
debit-XOR-credit invariant; the service layer mirrors the same check and
returns a friendlier 400 before the row ever reaches the database.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, Numeric, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class JournalLine(Base):
    __tablename__ = "journal_line"
    __table_args__ = (
        CheckConstraint(
            "(debit > 0 AND credit = 0) OR (credit > 0 AND debit = 0)",
            name="ck_journal_line_debit_xor_credit",
        ),
        Index("ix_journal_line_entry_id", "entry_id"),
        Index("ix_journal_line_account_entry", "account_id", "entry_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    entry_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("journal_entry.id", ondelete="RESTRICT"), nullable=False
    )

    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("account.id", ondelete="RESTRICT"), nullable=False
    )

    debit: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False, server_default="0")
    credit: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False, server_default="0")

    line_number: Mapped[int] = mapped_column(Integer, nullable=False)
    memo: Mapped[str | None] = mapped_column(Text(), nullable=True)

    entry = relationship("JournalEntry", back_populates="lines")
