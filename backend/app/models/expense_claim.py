"""ORM models for ``expense_claim`` + ``expense_claim_line`` (Phase 8.7, #134).

Expense claims are the AP-side employee-reimbursable aggregate. A
submitter (any logged-in user) drafts a claim with receipts (attachments
on the lines), submits it, and depending on the configured threshold it
either routes through the Phase 4.4 approvals queue or stays in
``submitted`` for owner/bookkeeper review. On approval the service posts
a balanced JE (Dr Expense per-line, Cr Employee-Reimbursable liability)
and stamps ``posting_journal_entry_id``. A subsequent Phase 8.3
``bill_payment`` against the liability completes the reimbursement —
when that bill_payment lands the operator calls ``mark_reimbursed`` to
stamp the FK and flip state to ``reimbursed``.

The single PG enum is auto-created by the 0045 migration. Per agents.md
gotcha #3, the ORM declares it with ``SAEnum(..., create_type=False)``.
"""

from __future__ import annotations

import enum
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
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
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class ExpenseClaimState(enum.StrEnum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    APPROVED = "approved"
    REJECTED = "rejected"
    REIMBURSED = "reimbursed"
    CANCELLED = "cancelled"


EXPENSE_CLAIM_STATE_VALUES: tuple[str, ...] = tuple(m.value for m in ExpenseClaimState)


EXPENSE_CLAIM_STATE_ENUM = SAEnum(
    ExpenseClaimState,
    name="expense_claim_state",
    values_callable=lambda enum_cls: [m.value for m in enum_cls],
    create_type=False,
)


_SA_FALSE = false()


class ExpenseClaim(Base):
    __tablename__ = "expense_claim"
    __table_args__ = (
        Index("ix_expense_claim_state", "state"),
        Index("ix_expense_claim_submitter_user_id", "submitter_user_id"),
        Index("ix_expense_claim_approval_request_id", "approval_request_id"),
        Index("ix_expense_claim_created_at_id", "created_at", "id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    claim_number: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)

    submitter_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("user.id", ondelete="RESTRICT"), nullable=False
    )

    state: Mapped[ExpenseClaimState] = mapped_column(
        EXPENSE_CLAIM_STATE_ENUM,
        nullable=False,
        default=ExpenseClaimState.DRAFT,
        server_default="draft",
    )

    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    approver_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )

    rejection_reason: Mapped[str | None] = mapped_column(Text(), nullable=True)

    total_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 6), nullable=False, default=Decimal("0"), server_default="0"
    )

    currency: Mapped[str] = mapped_column(
        String(3), nullable=False, default="USD", server_default="USD"
    )

    posting_journal_entry_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("journal_entry.id", ondelete="SET NULL"), nullable=True
    )

    approval_request_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("approval_request.id", ondelete="SET NULL"), nullable=True
    )

    reimbursement_payment_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("bill_payment.id", ondelete="SET NULL"), nullable=True
    )

    notes: Mapped[str | None] = mapped_column(Text(), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    lines: Mapped[list[ExpenseClaimLine]] = relationship(
        "ExpenseClaimLine",
        back_populates="claim",
        cascade="all, delete-orphan",
    )


class ExpenseClaimLine(Base):
    __tablename__ = "expense_claim_line"
    __table_args__ = (
        UniqueConstraint("claim_id", "line_number", name="uq_expense_claim_line_claim_line"),
        Index("ix_expense_claim_line_claim_id", "claim_id"),
        Index("ix_expense_claim_line_expense_category_id", "expense_category_id"),
        # Phase 8.8 (#135) indexes for the rebill-to-customer flow.
        Index("ix_expense_claim_line_customer_id", "customer_id"),
        Index("ix_expense_claim_line_is_billable", "is_billable"),
        Index("ix_expense_claim_line_billed_invoice_item_id", "billed_invoice_item_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    claim_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("expense_claim.id", ondelete="CASCADE"), nullable=False
    )
    line_number: Mapped[int] = mapped_column(Integer, nullable=False)

    expense_category_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("expense_category.id", ondelete="RESTRICT"), nullable=False
    )

    description: Mapped[str] = mapped_column(Text(), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    occurred_on: Mapped[date] = mapped_column(Date(), nullable=False)

    attachment_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("attachment.id", ondelete="SET NULL"), nullable=True
    )

    # Reserved for Phase 8.8 rebill-to-customer flow. Inert today.
    is_billable: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=_SA_FALSE
    )
    customer_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("customer.id", ondelete="SET NULL"), nullable=True
    )
    billed_invoice_item_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("invoice_item.id", ondelete="SET NULL"), nullable=True
    )
    markup_percent: Mapped[Decimal] = mapped_column(
        Numeric(7, 4), nullable=False, default=Decimal("0"), server_default="0"
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

    claim: Mapped[ExpenseClaim] = relationship("ExpenseClaim", back_populates="lines")
