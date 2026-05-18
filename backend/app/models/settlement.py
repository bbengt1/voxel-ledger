"""ORM models for ``settlement`` + ``settlement_line`` (Phase 9.8, #160).

A settlement is a marketplace payout statement (Etsy / Amazon / Shopify
/ generic CSV). Each row carries the per-period totals (gross / fees /
refunds / adjustments / payout) and links to the destination payout
account. Lines are the individual transactions inside the statement.

Per agents.md gotcha #1 the three enums (``settlement_state``,
``settlement_line_kind``, ``settlement_line_state``) are NOT pre-created
in the migration; ``op.create_table`` auto-creates the PG types via the
column dialect hook. Per gotcha #3 the ORM declares them with
``SAEnum(..., create_type=False, values_callable=...)``.
"""

from __future__ import annotations

import enum
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class SettlementState(enum.StrEnum):
    IMPORTED = "imported"
    MATCHED = "matched"
    POSTED = "posted"
    CANCELLED = "cancelled"


class SettlementLineKind(enum.StrEnum):
    SALE = "sale"
    REFUND = "refund"
    FEE = "fee"
    ADJUSTMENT = "adjustment"
    PAYOUT = "payout"
    TAX = "tax"


class SettlementLineState(enum.StrEnum):
    UNMATCHED = "unmatched"
    MATCHED = "matched"
    IGNORED = "ignored"


SETTLEMENT_STATE_VALUES: tuple[str, ...] = tuple(m.value for m in SettlementState)
SETTLEMENT_LINE_KIND_VALUES: tuple[str, ...] = tuple(m.value for m in SettlementLineKind)
SETTLEMENT_LINE_STATE_VALUES: tuple[str, ...] = tuple(m.value for m in SettlementLineState)


SETTLEMENT_STATE_ENUM = SAEnum(
    SettlementState,
    name="settlement_state",
    values_callable=lambda enum_cls: [m.value for m in enum_cls],
    create_type=False,
)
SETTLEMENT_LINE_KIND_ENUM = SAEnum(
    SettlementLineKind,
    name="settlement_line_kind",
    values_callable=lambda enum_cls: [m.value for m in enum_cls],
    create_type=False,
)
SETTLEMENT_LINE_STATE_ENUM = SAEnum(
    SettlementLineState,
    name="settlement_line_state",
    values_callable=lambda enum_cls: [m.value for m in enum_cls],
    create_type=False,
)


class Settlement(Base):
    __tablename__ = "settlement"
    __table_args__ = (
        Index("ix_settlement_channel_period_end", "channel_id", "period_end"),
        Index("ix_settlement_state", "state"),
        Index("ix_settlement_imported_at", "imported_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    settlement_number: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)

    channel_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sales_channel.id", ondelete="RESTRICT"), nullable=False
    )
    period_start: Mapped[date] = mapped_column(Date(), nullable=False)
    period_end: Mapped[date] = mapped_column(Date(), nullable=False)

    gross_amount: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    fee_amount: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    refund_amount: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    adjustment_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 6), nullable=False, default=Decimal("0"), server_default="0"
    )
    payout_amount: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)

    payout_account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("account.id", ondelete="RESTRICT"), nullable=False
    )

    filename: Mapped[str] = mapped_column(String(255), nullable=False)

    imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    imported_by_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("user.id", ondelete="RESTRICT"), nullable=False
    )

    state: Mapped[SettlementState] = mapped_column(
        SETTLEMENT_STATE_ENUM,
        nullable=False,
        default=SettlementState.IMPORTED,
        server_default="imported",
    )

    posting_journal_entry_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("journal_entry.id", ondelete="SET NULL"), nullable=True
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


class SettlementLine(Base):
    __tablename__ = "settlement_line"
    __table_args__ = (
        Index(
            "ix_settlement_line_settlement_line_number",
            "settlement_id",
            "line_number",
        ),
        Index(
            "ix_settlement_line_settlement_state",
            "settlement_id",
            "state",
        ),
        Index("ix_settlement_line_external_order_id", "external_order_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    settlement_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("settlement.id", ondelete="CASCADE"), nullable=False
    )
    line_number: Mapped[int] = mapped_column(Integer(), nullable=False)

    line_kind: Mapped[SettlementLineKind] = mapped_column(SETTLEMENT_LINE_KIND_ENUM, nullable=False)
    occurred_on: Mapped[date] = mapped_column(Date(), nullable=False)
    description: Mapped[str] = mapped_column(Text(), nullable=False, default="", server_default="")

    external_order_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    external_txn_id: Mapped[str | None] = mapped_column(String(128), nullable=True)

    amount: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)

    state: Mapped[SettlementLineState] = mapped_column(
        SETTLEMENT_LINE_STATE_ENUM,
        nullable=False,
        default=SettlementLineState.UNMATCHED,
        server_default="unmatched",
    )

    matched_sale_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("sale.id", ondelete="SET NULL"), nullable=True
    )
    matched_refund_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("refund.id", ondelete="SET NULL"), nullable=True
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
