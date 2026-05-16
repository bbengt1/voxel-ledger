"""ORM models for credit / debit notes (Phase 7.4, #112).

A ``credit_note`` is a post-issue correction that reduces the customer's
outstanding balance on an already-issued invoice (e.g. concession,
discount we forgot to add). It posts ``debit Revenue / credit AR`` at
issue time, reversing a proportional slice of the invoice's revenue.

A ``debit_note`` is the opposite — it INCREASES what the customer owes
on an already-issued invoice (e.g. shipping we forgot to charge). It
posts ``debit AR / credit Revenue``.

Each note carries its own reference number (``CN-YYYY-NNNN`` /
``DN-YYYY-NNNN``) and a state machine
(``draft -> issued -> applied | cancelled``).

Per agents.md gotcha #1 the ``credit_note_state`` and
``debit_note_state`` enums auto-create via the column dialect hook. Per
gotcha #3 the ORM declares them with
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
    String,
    Text,
    func,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class CreditNoteState(enum.StrEnum):
    DRAFT = "draft"
    ISSUED = "issued"
    APPLIED = "applied"
    CANCELLED = "cancelled"


class DebitNoteState(enum.StrEnum):
    DRAFT = "draft"
    ISSUED = "issued"
    APPLIED = "applied"
    CANCELLED = "cancelled"


CREDIT_NOTE_STATE_VALUES: tuple[str, ...] = tuple(m.value for m in CreditNoteState)
DEBIT_NOTE_STATE_VALUES: tuple[str, ...] = tuple(m.value for m in DebitNoteState)


CREDIT_NOTE_STATE_ENUM = SAEnum(
    CreditNoteState,
    name="credit_note_state",
    values_callable=lambda enum_cls: [m.value for m in enum_cls],
    create_type=False,
)

DEBIT_NOTE_STATE_ENUM = SAEnum(
    DebitNoteState,
    name="debit_note_state",
    values_callable=lambda enum_cls: [m.value for m in enum_cls],
    create_type=False,
)


class CreditNote(Base):
    __tablename__ = "credit_note"
    __table_args__ = (
        Index("ix_credit_note_state", "state"),
        Index("ix_credit_note_customer_id", "customer_id"),
        Index("ix_credit_note_invoice_id", "invoice_id"),
        Index("ix_credit_note_created_at_id", "created_at", "id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    credit_note_number: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)

    customer_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("customer.id", ondelete="RESTRICT"), nullable=False
    )
    invoice_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("invoice.id", ondelete="RESTRICT"), nullable=False
    )

    reason: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    total_amount: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)

    state: Mapped[CreditNoteState] = mapped_column(
        CREDIT_NOTE_STATE_ENUM,
        nullable=False,
        default=CreditNoteState.DRAFT,
        server_default="draft",
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


class DebitNote(Base):
    __tablename__ = "debit_note"
    __table_args__ = (
        Index("ix_debit_note_state", "state"),
        Index("ix_debit_note_customer_id", "customer_id"),
        Index("ix_debit_note_invoice_id", "invoice_id"),
        Index("ix_debit_note_created_at_id", "created_at", "id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    debit_note_number: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)

    customer_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("customer.id", ondelete="RESTRICT"), nullable=False
    )
    invoice_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("invoice.id", ondelete="RESTRICT"), nullable=False
    )

    reason: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    total_amount: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)

    state: Mapped[DebitNoteState] = mapped_column(
        DEBIT_NOTE_STATE_ENUM,
        nullable=False,
        default=DebitNoteState.DRAFT,
        server_default="draft",
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
