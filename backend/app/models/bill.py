"""ORM models for ``bill`` + ``bill_item`` (Phase 8.2, #129).

The bill is the AP system-of-record — the direct AP-side mirror of
the Phase 7.3 ``invoice``. Issuing a bill (``draft -> issued``) posts
to the GL atomically inside the same DB transaction: Dr Expense (per
line), Cr AP (total). Subsequent payments (Phase 8.3) draw down the
AP balance.

Per agents.md gotcha #1 the ``bill_state`` and ``bill_item_kind`` enums
are NOT pre-created in the migration — ``op.create_table`` autocreates
the PG types via the columns' dialect hook. Per gotcha #3 the ORM
declares them with ``SAEnum(*VALUES, name=..., create_type=False)``.

``expense_category_id`` is a bare UUID column today; Phase 8.6 lands the
``expense_category`` table and retro-fits the FK constraint via
migration. We keep the column nullable + non-FK so today's bills can
already attach a category UUID that gets validated downstream once 8.6
arrives.

``last_late_fee_applied_at`` is reserved for a future AP-side late-fee
analog (if any); included now to keep the schema parallel with
``invoice``.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class BillState(enum.StrEnum):
    DRAFT = "draft"
    ISSUED = "issued"
    PARTIALLY_PAID = "partially_paid"
    PAID = "paid"
    OVERDUE = "overdue"
    VOID = "void"


class BillItemKind(enum.StrEnum):
    EXPENSE_CATEGORY = "expense_category"
    MANUAL = "manual"


BILL_STATE_VALUES: tuple[str, ...] = tuple(m.value for m in BillState)
BILL_ITEM_KIND_VALUES: tuple[str, ...] = tuple(m.value for m in BillItemKind)


BILL_STATE_ENUM = SAEnum(
    BillState,
    name="bill_state",
    values_callable=lambda enum_cls: [m.value for m in enum_cls],
    create_type=False,
)

BILL_ITEM_KIND_ENUM = SAEnum(
    BillItemKind,
    name="bill_item_kind",
    values_callable=lambda enum_cls: [m.value for m in enum_cls],
    create_type=False,
)


class Bill(Base):
    __tablename__ = "bill"
    __table_args__ = (
        Index("ix_bill_state", "state"),
        Index("ix_bill_vendor_id", "vendor_id"),
        Index("ix_bill_created_at_id", "created_at", "id"),
        Index("ix_bill_issued_at", "issued_at"),
        Index("ix_bill_due_at", "due_at"),
        Index("ix_bill_state_due_at", "state", "due_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    bill_number: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)

    vendor_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("vendor.id", ondelete="RESTRICT"), nullable=False
    )

    state: Mapped[BillState] = mapped_column(
        BILL_STATE_ENUM,
        nullable=False,
        default=BillState.DRAFT,
        server_default="draft",
    )

    issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # The number the vendor printed on their bill — distinct from our
    # internal ``bill_number``. Useful for operator reconciliation.
    vendor_invoice_number: Mapped[str | None] = mapped_column(String(64), nullable=True)

    subtotal: Mapped[Decimal] = mapped_column(
        Numeric(18, 6), nullable=False, default=Decimal("0"), server_default="0"
    )
    discount_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 6), nullable=False, default=Decimal("0"), server_default="0"
    )
    tax_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 6), nullable=False, default=Decimal("0"), server_default="0"
    )
    total_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 6), nullable=False, default=Decimal("0"), server_default="0"
    )
    amount_paid: Mapped[Decimal] = mapped_column(
        Numeric(18, 6), nullable=False, default=Decimal("0"), server_default="0"
    )
    amount_outstanding: Mapped[Decimal] = mapped_column(
        Numeric(18, 6), nullable=False, default=Decimal("0"), server_default="0"
    )

    currency: Mapped[str] = mapped_column(
        String(3), nullable=False, default="USD", server_default="USD"
    )

    notes: Mapped[str | None] = mapped_column(Text(), nullable=True)

    billing_address_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    posting_journal_entry_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("journal_entry.id", ondelete="RESTRICT"), nullable=True
    )

    last_late_fee_applied_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
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

    items: Mapped[list[BillItem]] = relationship(
        "BillItem",
        back_populates="bill",
        cascade="all, delete-orphan",
        order_by="BillItem.line_number",
    )


class BillItem(Base):
    __tablename__ = "bill_item"
    __table_args__ = (
        UniqueConstraint("bill_id", "line_number", name="uq_bill_item_bill_line"),
        CheckConstraint(
            "(kind = 'expense_category' AND expense_category_id IS NOT NULL) OR "
            "(kind = 'manual')",
            name="ck_bill_item_kind_ref",
        ),
        Index("ix_bill_item_bill_id", "bill_id"),
        Index("ix_bill_item_expense_category_id", "expense_category_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    bill_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("bill.id", ondelete="CASCADE"), nullable=False
    )
    line_number: Mapped[int] = mapped_column(Integer(), nullable=False)

    kind: Mapped[BillItemKind] = mapped_column(BILL_ITEM_KIND_ENUM, nullable=False)

    # FK to ``expense_category`` added by Phase 8.6 (0044) — the column
    # itself was introduced by Phase 8.2 as a bare UUID.
    expense_category_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("expense_category.id", ondelete="RESTRICT"), nullable=True
    )

    description: Mapped[str] = mapped_column(Text(), nullable=False)
    vendor_sku: Mapped[str | None] = mapped_column(String(64), nullable=True)

    quantity: Mapped[Decimal] = mapped_column(
        Numeric(18, 6), nullable=False, default=Decimal("1"), server_default="1"
    )
    unit_price: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    extended_amount: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)

    expense_account_id_override: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("account.id", ondelete="RESTRICT"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    bill: Mapped[Bill] = relationship("Bill", back_populates="items")
