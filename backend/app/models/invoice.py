"""ORM models for ``invoice`` + ``invoice_item`` (Phase 7.3, #111).

The invoice is the AR system-of-record: a numbered, addressed bill to a
customer with a due date. Issuing an invoice (``draft -> issued``) posts
to the GL atomically inside the same DB transaction; subsequent payments
draw down the AR balance (Phase 7.4).

Per agents.md gotcha #1 the ``invoice_state`` and ``invoice_item_kind``
enums are NOT pre-created in the migration — ``op.create_table``
autocreates the PG types via the columns' dialect hook. Per gotcha #3
the ORM declares them with ``SAEnum(*VALUES, name=..., create_type=False)``.

``overdue`` is a derived state: a Phase 7.6 worker scans
``due_at < now() AND state IN (issued, partially_paid)`` and transitions
the row. Today we just allow it as a state value.

``posting_journal_entry_id`` parallels Phase 6.3's pattern on ``sale``:
the FK to the JE that the issue/post pipeline created; the void path
looks up the entry to reverse via this column rather than scanning the
GL by description.
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


class InvoiceState(enum.StrEnum):
    DRAFT = "draft"
    ISSUED = "issued"
    PARTIALLY_PAID = "partially_paid"
    PAID = "paid"
    OVERDUE = "overdue"
    VOID = "void"


class InvoiceItemKind(enum.StrEnum):
    PRODUCT = "product"
    JOB = "job"
    MANUAL = "manual"


INVOICE_STATE_VALUES: tuple[str, ...] = tuple(m.value for m in InvoiceState)
INVOICE_ITEM_KIND_VALUES: tuple[str, ...] = tuple(m.value for m in InvoiceItemKind)


INVOICE_STATE_ENUM = SAEnum(
    InvoiceState,
    name="invoice_state",
    values_callable=lambda enum_cls: [m.value for m in enum_cls],
    create_type=False,
)

INVOICE_ITEM_KIND_ENUM = SAEnum(
    InvoiceItemKind,
    name="invoice_item_kind",
    values_callable=lambda enum_cls: [m.value for m in enum_cls],
    create_type=False,
)


class Invoice(Base):
    __tablename__ = "invoice"
    __table_args__ = (
        Index("ix_invoice_state", "state"),
        Index("ix_invoice_customer_id", "customer_id"),
        Index("ix_invoice_quote_id", "quote_id"),
        Index("ix_invoice_sale_id", "sale_id"),
        Index("ix_invoice_created_at_id", "created_at", "id"),
        Index("ix_invoice_issued_at", "issued_at"),
        Index("ix_invoice_due_at", "due_at"),
        Index("ix_invoice_state_due_at", "state", "due_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    invoice_number: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)

    customer_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("customer.id", ondelete="RESTRICT"), nullable=False
    )

    # quote_id is FK to ``quote.id`` (set when this invoice was converted
    # from a quote). Nullable.
    quote_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("quote.id", ondelete="RESTRICT"), nullable=True
    )

    # sale_id is FK to ``sale.id`` (set when generated from a sale —
    # alternate flow; ``create_from_sale`` is stubbed today, see
    # invoices service docstring).
    sale_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("sale.id", ondelete="RESTRICT"), nullable=True
    )

    state: Mapped[InvoiceState] = mapped_column(
        INVOICE_STATE_ENUM,
        nullable=False,
        default=InvoiceState.DRAFT,
        server_default="draft",
    )

    issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

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

    # Phase 7.6: last wall-clock time the late-fee worker emitted a debit
    # note against this invoice. Compared to ``now - compound_interval_days``
    # to gate re-application; ``None`` means no late fee has been applied.
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

    items: Mapped[list[InvoiceItem]] = relationship(
        "InvoiceItem",
        back_populates="invoice",
        cascade="all, delete-orphan",
        order_by="InvoiceItem.line_number",
    )


class InvoiceItem(Base):
    __tablename__ = "invoice_item"
    __table_args__ = (
        UniqueConstraint("invoice_id", "line_number", name="uq_invoice_item_invoice_line"),
        CheckConstraint(
            "(kind = 'product' AND product_id IS NOT NULL AND job_id IS NULL) OR "
            "(kind = 'job' AND job_id IS NOT NULL AND product_id IS NULL) OR "
            "(kind = 'manual' AND product_id IS NULL AND job_id IS NULL)",
            name="ck_invoice_item_kind_ref",
        ),
        Index("ix_invoice_item_invoice_id", "invoice_id"),
        Index("ix_invoice_item_product_id", "product_id"),
        Index("ix_invoice_item_job_id", "job_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    invoice_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("invoice.id", ondelete="CASCADE"), nullable=False
    )
    line_number: Mapped[int] = mapped_column(Integer(), nullable=False)

    kind: Mapped[InvoiceItemKind] = mapped_column(INVOICE_ITEM_KIND_ENUM, nullable=False)

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
    extended_amount: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    invoice: Mapped[Invoice] = relationship("Invoice", back_populates="items")
