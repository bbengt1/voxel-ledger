"""ORM models for ``recurring_invoice_template`` + items (Phase 7.5, #113).

A recurring invoice template is the operator-configured subscription / retainer
cadence: every N daily/weekly/monthly/quarterly/yearly the worker materializes
a draft invoice (or auto-issued invoice if ``auto_issue=True``) for the
customer.

Per agents.md gotcha #1 the ``recurring_cadence_kind`` and
``recurring_template_state`` enums are NOT pre-created in the migration —
``op.create_table`` autocreates the PG types via the columns' dialect hook.
Per gotcha #3 the ORM declares them with
``SAEnum(*VALUES, name=..., create_type=False)``.

The line items mirror ``invoice_item`` but intentionally omit
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


class RecurringCadenceKind(enum.StrEnum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    YEARLY = "yearly"


class RecurringTemplateState(enum.StrEnum):
    ACTIVE = "active"
    PAUSED = "paused"
    CANCELLED = "cancelled"


class RecurringInvoiceItemKind(enum.StrEnum):
    PRODUCT = "product"
    JOB = "job"
    MANUAL = "manual"


RECURRING_CADENCE_KIND_VALUES: tuple[str, ...] = tuple(m.value for m in RecurringCadenceKind)
RECURRING_TEMPLATE_STATE_VALUES: tuple[str, ...] = tuple(m.value for m in RecurringTemplateState)


RECURRING_CADENCE_KIND_ENUM = SAEnum(
    RecurringCadenceKind,
    name="recurring_cadence_kind",
    values_callable=lambda enum_cls: [m.value for m in enum_cls],
    create_type=False,
)

RECURRING_TEMPLATE_STATE_ENUM = SAEnum(
    RecurringTemplateState,
    name="recurring_template_state",
    values_callable=lambda enum_cls: [m.value for m in enum_cls],
    create_type=False,
)

# Reuse the existing ``invoice_item_kind`` PG enum (Phase 7.3) for line kinds
# so we don't proliferate enums. SQLAlchemy declares it via the existing
# invoice_item_kind PG type name.
RECURRING_INVOICE_ITEM_KIND_ENUM = SAEnum(
    RecurringInvoiceItemKind,
    name="invoice_item_kind",
    values_callable=lambda enum_cls: [m.value for m in enum_cls],
    create_type=False,
)


class RecurringInvoiceTemplate(Base):
    __tablename__ = "recurring_invoice_template"
    __table_args__ = (
        Index("ix_recurring_invoice_template_customer_id", "customer_id"),
        Index("ix_recurring_invoice_template_state", "state"),
        Index("ix_recurring_invoice_template_next_issue_at", "next_issue_at"),
        Index("ix_recurring_invoice_template_created_at_id", "created_at", "id"),
        CheckConstraint(
            "cadence_interval >= 1",
            name="ck_recurring_invoice_template_cadence_interval_positive",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    customer_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("customer.id", ondelete="RESTRICT"), nullable=False
    )

    name: Mapped[str] = mapped_column(String(200), nullable=False)

    cadence_kind: Mapped[RecurringCadenceKind] = mapped_column(
        RECURRING_CADENCE_KIND_ENUM,
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

    state: Mapped[RecurringTemplateState] = mapped_column(
        RECURRING_TEMPLATE_STATE_ENUM,
        nullable=False,
        default=RecurringTemplateState.ACTIVE,
        server_default="active",
    )

    notes: Mapped[str | None] = mapped_column(Text(), nullable=True)

    # Default-line overrides (applied at materialize time)
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

    items: Mapped[list[RecurringInvoiceTemplateItem]] = relationship(
        "RecurringInvoiceTemplateItem",
        back_populates="template",
        cascade="all, delete-orphan",
        order_by="RecurringInvoiceTemplateItem.line_number",
    )


class RecurringInvoiceTemplateItem(Base):
    __tablename__ = "recurring_invoice_template_item"
    __table_args__ = (
        UniqueConstraint(
            "template_id", "line_number", name="uq_recurring_invoice_template_item_line"
        ),
        CheckConstraint(
            "(kind = 'product' AND product_id IS NOT NULL AND job_id IS NULL) OR "
            "(kind = 'job' AND job_id IS NOT NULL AND product_id IS NULL) OR "
            "(kind = 'manual' AND product_id IS NULL AND job_id IS NULL)",
            name="ck_recurring_invoice_template_item_kind_ref",
        ),
        Index("ix_recurring_invoice_template_item_template_id", "template_id"),
        Index("ix_recurring_invoice_template_item_product_id", "product_id"),
        Index("ix_recurring_invoice_template_item_job_id", "job_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    template_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("recurring_invoice_template.id", ondelete="CASCADE"), nullable=False
    )
    line_number: Mapped[int] = mapped_column(Integer(), nullable=False)

    kind: Mapped[RecurringInvoiceItemKind] = mapped_column(
        RECURRING_INVOICE_ITEM_KIND_ENUM, nullable=False
    )

    product_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("product.id", ondelete="RESTRICT"), nullable=True
    )
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("job.id", ondelete="RESTRICT"), nullable=True
    )

    description: Mapped[str] = mapped_column(Text(), nullable=False)
    sku_or_job_number: Mapped[str | None] = mapped_column(String(64), nullable=True)

    quantity: Mapped[Decimal] = mapped_column(
        Numeric(18, 6), nullable=False, default=Decimal("1"), server_default="1"
    )
    unit_price: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    template: Mapped[RecurringInvoiceTemplate] = relationship(
        "RecurringInvoiceTemplate", back_populates="items"
    )
