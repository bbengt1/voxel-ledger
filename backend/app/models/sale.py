"""ORM models for ``sale`` + ``sale_item`` (Phase 6.2, #94).

A sale is the system-of-record for "this customer paid us this amount on
this channel for these items on this date." Lines reference either a
product (catalog item) or a job (production run) or are free-form manual
entries. Exactly one of ``product_id`` / ``job_id`` is set, OR both are
null for ``kind=manual`` — enforced by a CHECK constraint at the DB and
by the service layer.

``state`` is a PG enum (``sale_state``) and ``sale_item.kind`` is a PG
enum (``sale_item_kind``) — both auto-created by the 0027 migration via
``op.create_table``. Per agents.md gotcha #3, the ORM declares them with
``SAEnum(*VALUES, name=..., create_type=False)`` so PG comparisons stay
typed.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
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


class SaleState(enum.StrEnum):
    DRAFT = "draft"
    CONFIRMED = "confirmed"
    FULFILLED = "fulfilled"
    CANCELLED = "cancelled"


class SaleItemKind(enum.StrEnum):
    PRODUCT = "product"
    JOB = "job"
    MANUAL = "manual"


SALE_STATE_VALUES: tuple[str, ...] = tuple(m.value for m in SaleState)
SALE_ITEM_KIND_VALUES: tuple[str, ...] = tuple(m.value for m in SaleItemKind)


SALE_STATE_ENUM = SAEnum(
    SaleState,
    name="sale_state",
    values_callable=lambda enum_cls: [m.value for m in enum_cls],
    create_type=False,
)

SALE_ITEM_KIND_ENUM = SAEnum(
    SaleItemKind,
    name="sale_item_kind",
    values_callable=lambda enum_cls: [m.value for m in enum_cls],
    create_type=False,
)


class Sale(Base):
    __tablename__ = "sale"
    __table_args__ = (
        Index("ix_sale_state", "state"),
        Index("ix_sale_channel_id", "channel_id"),
        Index("ix_sale_occurred_at", "occurred_at"),
        Index("ix_sale_created_at_id", "created_at", "id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    sale_number: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)

    channel_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sales_channel.id", ondelete="RESTRICT"), nullable=False
    )
    external_order_id: Mapped[str | None] = mapped_column(Text(), nullable=True)

    customer_name: Mapped[str] = mapped_column(String(255), nullable=False)
    customer_email: Mapped[str | None] = mapped_column(String(255), nullable=True)

    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    subtotal: Mapped[Decimal] = mapped_column(
        Numeric(18, 6), nullable=False, default=Decimal("0"), server_default="0"
    )
    discount_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 6), nullable=False, default=Decimal("0"), server_default="0"
    )
    shipping_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 6), nullable=False, default=Decimal("0"), server_default="0"
    )
    tax_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 6), nullable=False, default=Decimal("0"), server_default="0"
    )
    channel_fee_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 6), nullable=False, default=Decimal("0"), server_default="0"
    )
    total_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 6), nullable=False, default=Decimal("0"), server_default="0"
    )

    state: Mapped[SaleState] = mapped_column(
        SALE_STATE_ENUM,
        nullable=False,
        default=SaleState.DRAFT,
        server_default="draft",
    )
    notes: Mapped[str | None] = mapped_column(Text(), nullable=True)

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

    items: Mapped[list[SaleItem]] = relationship(
        "SaleItem",
        back_populates="sale",
        cascade="all, delete-orphan",
        order_by="SaleItem.line_number",
    )


class SaleItem(Base):
    __tablename__ = "sale_item"
    __table_args__ = (
        UniqueConstraint("sale_id", "line_number", name="uq_sale_item_sale_line"),
        CheckConstraint(
            "(kind = 'product' AND product_id IS NOT NULL AND job_id IS NULL) OR "
            "(kind = 'job' AND job_id IS NOT NULL AND product_id IS NULL) OR "
            "(kind = 'manual' AND product_id IS NULL AND job_id IS NULL)",
            name="ck_sale_item_kind_ref",
        ),
        Index("ix_sale_item_sale_id", "sale_id"),
        Index("ix_sale_item_product_id", "product_id"),
        Index("ix_sale_item_job_id", "job_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    sale_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sale.id", ondelete="CASCADE"), nullable=False
    )
    line_number: Mapped[int] = mapped_column(Integer(), nullable=False)

    kind: Mapped[SaleItemKind] = mapped_column(SALE_ITEM_KIND_ENUM, nullable=False)

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

    sale: Mapped[Sale] = relationship("Sale", back_populates="items")
