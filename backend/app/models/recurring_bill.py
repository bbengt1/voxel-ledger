"""ORM models for ``recurring_bill_template`` + items (Phase 8.5, #132).

The AP-side mirror of Phase 7.5's ``recurring_invoice_template``: a
recurring bill template is the operator-configured AP subscription
cadence. Every N daily/weekly/monthly/quarterly/yearly the worker
materializes a draft bill (or auto-issued bill if ``auto_issue=True``)
for the vendor.

Per agents.md gotcha #1 the ``recurring_bill_cadence_kind`` and
``recurring_bill_template_state`` enums are NOT pre-created in the
migration — ``op.create_table`` autocreates the PG types via the
columns' dialect hook. Per gotcha #3 the ORM declares them with
``SAEnum(*VALUES, name=..., create_type=False)``. The line-item ``kind``
column reuses the existing ``bill_item_kind`` PG enum (Phase 8.2).

The line items mirror ``bill_item`` but intentionally omit
``extended_amount`` — it is recomputed at materialize time.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
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


class RecurringBillCadenceKind(enum.StrEnum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    YEARLY = "yearly"


class RecurringBillTemplateState(enum.StrEnum):
    ACTIVE = "active"
    PAUSED = "paused"
    CANCELLED = "cancelled"


class RecurringBillItemKind(enum.StrEnum):
    EXPENSE_CATEGORY = "expense_category"
    MANUAL = "manual"


RECURRING_BILL_CADENCE_KIND_VALUES: tuple[str, ...] = tuple(
    m.value for m in RecurringBillCadenceKind
)
RECURRING_BILL_TEMPLATE_STATE_VALUES: tuple[str, ...] = tuple(
    m.value for m in RecurringBillTemplateState
)


RECURRING_BILL_CADENCE_KIND_ENUM = SAEnum(
    RecurringBillCadenceKind,
    name="recurring_bill_cadence_kind",
    values_callable=lambda enum_cls: [m.value for m in enum_cls],
    create_type=False,
)

RECURRING_BILL_TEMPLATE_STATE_ENUM = SAEnum(
    RecurringBillTemplateState,
    name="recurring_bill_template_state",
    values_callable=lambda enum_cls: [m.value for m in enum_cls],
    create_type=False,
)

# Reuse the existing ``bill_item_kind`` PG enum (Phase 8.2).
RECURRING_BILL_ITEM_KIND_ENUM = SAEnum(
    RecurringBillItemKind,
    name="bill_item_kind",
    values_callable=lambda enum_cls: [m.value for m in enum_cls],
    create_type=False,
)


class RecurringBillTemplate(Base):
    __tablename__ = "recurring_bill_template"
    __table_args__ = (
        Index("ix_recurring_bill_template_vendor_id", "vendor_id"),
        Index("ix_recurring_bill_template_state", "state"),
        Index("ix_recurring_bill_template_next_issue_at", "next_issue_at"),
        Index("ix_recurring_bill_template_created_at_id", "created_at", "id"),
        CheckConstraint(
            "cadence_interval >= 1",
            name="ck_recurring_bill_template_cadence_interval_positive",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    vendor_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("vendor.id", ondelete="RESTRICT"), nullable=False
    )

    name: Mapped[str] = mapped_column(String(200), nullable=False)

    cadence_kind: Mapped[RecurringBillCadenceKind] = mapped_column(
        RECURRING_BILL_CADENCE_KIND_ENUM,
        nullable=False,
    )
    cadence_interval: Mapped[int] = mapped_column(
        Integer(), nullable=False, default=1, server_default="1"
    )

    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_issue_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    auto_issue: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=False)

    state: Mapped[RecurringBillTemplateState] = mapped_column(
        RECURRING_BILL_TEMPLATE_STATE_ENUM,
        nullable=False,
        default=RecurringBillTemplateState.ACTIVE,
        server_default="active",
    )

    notes: Mapped[str | None] = mapped_column(Text(), nullable=True)

    discount_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 6), nullable=False, default=Decimal("0"), server_default="0"
    )
    tax_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 6), nullable=False, default=Decimal("0"), server_default="0"
    )
    currency: Mapped[str] = mapped_column(
        String(3), nullable=False, default="USD", server_default="USD"
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

    items: Mapped[list[RecurringBillTemplateItem]] = relationship(
        "RecurringBillTemplateItem",
        back_populates="template",
        cascade="all, delete-orphan",
        order_by="RecurringBillTemplateItem.line_number",
    )


class RecurringBillTemplateItem(Base):
    __tablename__ = "recurring_bill_template_item"
    __table_args__ = (
        UniqueConstraint("template_id", "line_number", name="uq_recurring_bill_template_item_line"),
        CheckConstraint(
            "(kind = 'manual' AND expense_category_id IS NULL) OR "
            "(kind = 'expense_category' AND expense_category_id IS NOT NULL)",
            name="ck_recurring_bill_template_item_kind_ref",
        ),
        Index("ix_recurring_bill_template_item_template_id", "template_id"),
        Index("ix_recurring_bill_template_item_expense_category_id", "expense_category_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    template_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("recurring_bill_template.id", ondelete="CASCADE"), nullable=False
    )
    line_number: Mapped[int] = mapped_column(Integer(), nullable=False)

    kind: Mapped[RecurringBillItemKind] = mapped_column(
        RECURRING_BILL_ITEM_KIND_ENUM, nullable=False
    )

    # FK to ``expense_category`` added by Phase 8.6 (0044). The column
    # was introduced by Phase 8.5 as a bare UUID.
    expense_category_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("expense_category.id", ondelete="RESTRICT"), nullable=True
    )

    description: Mapped[str] = mapped_column(Text(), nullable=False)
    vendor_sku: Mapped[str | None] = mapped_column(String(64), nullable=True)

    quantity: Mapped[Decimal] = mapped_column(
        Numeric(18, 6), nullable=False, default=Decimal("1"), server_default="1"
    )
    unit_price: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    template: Mapped[RecurringBillTemplate] = relationship(
        "RecurringBillTemplate", back_populates="items"
    )
