"""ORM models for ``quote`` + ``quote_item`` (Phase 7.2, #110).

A quote is the pre-invoice: a numbered offer to a customer for a set of
products / jobs / line items with a validity window. Operators send it,
the customer accepts (or doesn't), and on acceptance it converts into an
invoice. The shape is intentionally very close to a sale + invoice but
quotes don't post to the ledger and don't move inventory.

Per agents.md gotcha #1 the ``quote_state`` and ``quote_item_kind``
enums are NOT pre-created in the migration — ``op.create_table``
autocreates the PG types via the columns' dialect hook. Per gotcha #3
the ORM declares them with ``SAEnum(*VALUES, name=..., create_type=False)``.

``accepted_invoice_id`` is a forward-declared UUID column: the FK
constraint will be added by the Phase 7.3 ``invoice`` migration. It is
nullable today and has no FK target.
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


class QuoteState(enum.StrEnum):
    DRAFT = "draft"
    SENT = "sent"
    ACCEPTED = "accepted"
    DECLINED = "declined"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class QuoteItemKind(enum.StrEnum):
    PRODUCT = "product"
    JOB = "job"
    MANUAL = "manual"


QUOTE_STATE_VALUES: tuple[str, ...] = tuple(m.value for m in QuoteState)
QUOTE_ITEM_KIND_VALUES: tuple[str, ...] = tuple(m.value for m in QuoteItemKind)


QUOTE_STATE_ENUM = SAEnum(
    QuoteState,
    name="quote_state",
    values_callable=lambda enum_cls: [m.value for m in enum_cls],
    create_type=False,
)

QUOTE_ITEM_KIND_ENUM = SAEnum(
    QuoteItemKind,
    name="quote_item_kind",
    values_callable=lambda enum_cls: [m.value for m in enum_cls],
    create_type=False,
)


class Quote(Base):
    __tablename__ = "quote"
    __table_args__ = (
        Index("ix_quote_state", "state"),
        Index("ix_quote_customer_id", "customer_id"),
        Index("ix_quote_created_at_id", "created_at", "id"),
        Index("ix_quote_issued_at", "issued_at"),
        Index("ix_quote_valid_until", "valid_until"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    quote_number: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)

    customer_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("customer.id", ondelete="RESTRICT"), nullable=False
    )

    state: Mapped[QuoteState] = mapped_column(
        QUOTE_STATE_ENUM,
        nullable=False,
        default=QuoteState.DRAFT,
        server_default="draft",
    )

    issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

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

    notes: Mapped[str | None] = mapped_column(Text(), nullable=True)

    billing_address_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Forward declaration — Phase 7.3 migration adds the FK constraint to
    # ``invoice.id``. The column is nullable + bare UUID today.
    accepted_invoice_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)

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

    items: Mapped[list[QuoteItem]] = relationship(
        "QuoteItem",
        back_populates="quote",
        cascade="all, delete-orphan",
        order_by="QuoteItem.line_number",
    )


class QuoteItem(Base):
    __tablename__ = "quote_item"
    __table_args__ = (
        UniqueConstraint("quote_id", "line_number", name="uq_quote_item_quote_line"),
        CheckConstraint(
            "(kind = 'product' AND product_id IS NOT NULL AND job_id IS NULL) OR "
            "(kind = 'job' AND job_id IS NOT NULL AND product_id IS NULL) OR "
            "(kind = 'manual' AND product_id IS NULL AND job_id IS NULL)",
            name="ck_quote_item_kind_ref",
        ),
        Index("ix_quote_item_quote_id", "quote_id"),
        Index("ix_quote_item_product_id", "product_id"),
        Index("ix_quote_item_job_id", "job_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    quote_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("quote.id", ondelete="CASCADE"), nullable=False
    )
    line_number: Mapped[int] = mapped_column(Integer(), nullable=False)

    kind: Mapped[QuoteItemKind] = mapped_column(QUOTE_ITEM_KIND_ENUM, nullable=False)

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

    quote: Mapped[Quote] = relationship("Quote", back_populates="items")
