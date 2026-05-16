"""ORM models for ``refund`` + ``refund_item`` (Phase 6.5, #97).

A refund references an originating ``sale``. Lines reference the
originating ``sale_item`` (partial-line refunds are supported). Refund
posting reverses a proportional slice of the sale's inventory + journal
entry — see ``app.services.refunds`` for the orchestration.

Two PG enums are auto-created by the 0030 migration. Per agents.md
gotcha #3, the ORM declares them with ``SAEnum(..., create_type=False)``.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    false,
    func,
    true,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class RefundKind(enum.StrEnum):
    FULL = "full"
    PARTIAL = "partial"
    STORE_CREDIT = "store_credit"
    MARKETPLACE_INITIATED = "marketplace_initiated"


class RefundState(enum.StrEnum):
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    POSTED = "posted"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


REFUND_KIND_VALUES: tuple[str, ...] = tuple(m.value for m in RefundKind)
REFUND_STATE_VALUES: tuple[str, ...] = tuple(m.value for m in RefundState)


REFUND_KIND_ENUM = SAEnum(
    RefundKind,
    name="refund_kind",
    values_callable=lambda enum_cls: [m.value for m in enum_cls],
    create_type=False,
)

REFUND_STATE_ENUM = SAEnum(
    RefundState,
    name="refund_state",
    values_callable=lambda enum_cls: [m.value for m in enum_cls],
    create_type=False,
)


# Cross-dialect false()/true() — sa.false() / sa.true() are dialect-aware.
# We need them imported individually to use as server_default values.
_SA_TRUE = true()
_SA_FALSE = false()


class Refund(Base):
    __tablename__ = "refund"
    __table_args__ = (
        Index("ix_refund_state", "state"),
        Index("ix_refund_sale_id", "sale_id"),
        Index("ix_refund_created_at_id", "created_at", "id"),
        Index("ix_refund_approval_request_id", "approval_request_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    refund_number: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)

    sale_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sale.id", ondelete="RESTRICT"), nullable=False
    )

    kind: Mapped[RefundKind] = mapped_column(REFUND_KIND_ENUM, nullable=False)
    state: Mapped[RefundState] = mapped_column(
        REFUND_STATE_ENUM,
        nullable=False,
        default=RefundState.PENDING_APPROVAL,
        server_default="pending_approval",
    )

    total_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 6), nullable=False, default=Decimal("0"), server_default="0"
    )
    restock_inventory: Mapped[bool] = mapped_column(
        Boolean(), nullable=False, default=True, server_default=_SA_TRUE
    )
    reason_code: Mapped[str] = mapped_column(String(64), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text(), nullable=True)

    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("user.id", ondelete="RESTRICT"), nullable=False
    )
    approved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )
    approval_request_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("approval_request.id", ondelete="SET NULL"), nullable=True
    )

    # Populated by the refund post() step. Points at the reversing entry.
    posting_journal_entry_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("journal_entry.id", ondelete="SET NULL"), nullable=True
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

    items: Mapped[list[RefundItem]] = relationship(
        "RefundItem",
        back_populates="refund",
        cascade="all, delete-orphan",
    )


class RefundItem(Base):
    __tablename__ = "refund_item"
    __table_args__ = (
        UniqueConstraint("refund_id", "sale_item_id", name="uq_refund_item_refund_sale_item"),
        Index("ix_refund_item_refund_id", "refund_id"),
        Index("ix_refund_item_sale_item_id", "sale_item_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    refund_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("refund.id", ondelete="CASCADE"), nullable=False
    )
    sale_item_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sale_item.id", ondelete="RESTRICT"), nullable=False
    )

    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    unit_amount: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    extended_amount: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    refund: Mapped[Refund] = relationship("Refund", back_populates="items")
