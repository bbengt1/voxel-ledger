"""ORM models for ``pos_cart`` + ``pos_cart_item`` (Phase 6.4, #96).

The POS cart is a stateful server-side checkout session. It carries the
operator + channel + a line set built by barcode scans, plus an optional
line / cart discount. Checkout converts the cart into a ``sale`` via
:func:`app.services.sales.create_draft` + ``confirm`` in the same TX so
the Phase 6.3 inventory + journal posting fires atomically.

``state`` is a PG enum (``pos_cart_state``) auto-created by the 0030
migration via ``op.create_table``. Per agents.md gotcha #3 the ORM
declares it with ``SAEnum(..., create_type=False)`` so PG comparisons
stay typed.
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


class PosCartState(enum.StrEnum):
    OPEN = "open"
    CHECKED_OUT = "checked_out"
    VOIDED = "voided"


POS_CART_STATE_VALUES: tuple[str, ...] = tuple(m.value for m in PosCartState)


POS_CART_STATE_ENUM = SAEnum(
    PosCartState,
    name="pos_cart_state",
    values_callable=lambda enum_cls: [m.value for m in enum_cls],
    create_type=False,
)


class PosCart(Base):
    __tablename__ = "pos_cart"
    __table_args__ = (
        Index("ix_pos_cart_state", "state"),
        Index("ix_pos_cart_cashier_user_id", "cashier_user_id"),
        Index("ix_pos_cart_channel_id", "channel_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    cashier_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("user.id", ondelete="RESTRICT"), nullable=False
    )
    channel_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sales_channel.id", ondelete="RESTRICT"), nullable=False
    )

    state: Mapped[PosCartState] = mapped_column(
        POS_CART_STATE_ENUM,
        nullable=False,
        default=PosCartState.OPEN,
        server_default="open",
    )

    # Phase 7.1 (#109): FK to the real ``customer`` aggregate. Optional —
    # POS walk-ins typically don't pick a customer. When set, this is the
    # AR grouping key; the snapshot fields below stay populated for
    # receipt display.
    customer_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("customer.id", ondelete="SET NULL"), nullable=True
    )

    customer_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    customer_email: Mapped[str | None] = mapped_column(String(255), nullable=True)

    discount_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 6), nullable=False, default=Decimal("0"), server_default="0"
    )
    # ``percent`` or ``amount`` — ``None`` means no cart-level discount.
    discount_kind: Mapped[str | None] = mapped_column(String(16), nullable=True)

    # Per-cart tax profile override. ``NULL`` means "fall back to the
    # channel's tax profile." Operators can flip this in the POS UI for
    # one-off jurisdictions or exempt sales without changing the
    # channel default.
    tax_profile_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("tax_profile.id", ondelete="SET NULL"), nullable=True
    )

    # Populated once the cart checks out.
    sale_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("sale.id", ondelete="SET NULL"), nullable=True
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

    items: Mapped[list[PosCartItem]] = relationship(
        "PosCartItem",
        back_populates="cart",
        cascade="all, delete-orphan",
        order_by="PosCartItem.line_number",
    )


class PosCartItem(Base):
    __tablename__ = "pos_cart_item"
    __table_args__ = (
        UniqueConstraint("cart_id", "line_number", name="uq_pos_cart_item_cart_line"),
        Index("ix_pos_cart_item_cart_id", "cart_id"),
        Index("ix_pos_cart_item_product_id", "product_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    cart_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("pos_cart.id", ondelete="CASCADE"), nullable=False
    )
    line_number: Mapped[int] = mapped_column(Integer(), nullable=False)

    product_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("product.id", ondelete="RESTRICT"), nullable=True
    )

    description: Mapped[str] = mapped_column(Text(), nullable=False)
    sku: Mapped[str | None] = mapped_column(String(64), nullable=True)

    quantity: Mapped[Decimal] = mapped_column(
        Numeric(18, 6), nullable=False, default=Decimal("1"), server_default="1"
    )
    unit_price: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)

    discount_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 6), nullable=False, default=Decimal("0"), server_default="0"
    )
    # ``percent`` or ``amount`` — ``None`` means no per-line discount.
    discount_kind: Mapped[str | None] = mapped_column(String(16), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    cart: Mapped[PosCart] = relationship("PosCart", back_populates="items")
