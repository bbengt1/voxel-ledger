"""ORM model for the ``sales_channel`` table (Phase 6.1, #93).

A sales channel is where a sale originates: in-person POS, a marketplace
(Etsy, eBay), a direct web store (Shopify), wholesale, or other. Each
channel has its own fee model so later sales features (marketplace
settlement matching in Phase 9, channel-aware revenue accounts, etc.)
can hang off this row.

``kind`` and ``fee_model`` are PG enums (``sales_channel_kind`` /
``sales_channel_fee_model``) auto-created by the 0026 migration via
``op.create_table`` (agents.md gotcha #1). Per gotcha #3 the ORM declares
them with ``SAEnum(..., create_type=False)`` so PG comparisons stay typed.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Numeric, String, Text, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class SalesChannelKind(enum.StrEnum):
    POS = "pos"
    MARKETPLACE = "marketplace"
    DIRECT_WEB = "direct_web"
    WHOLESALE = "wholesale"
    OTHER = "other"


class SalesChannelFeeModel(enum.StrEnum):
    NONE = "none"
    FLAT = "flat"
    PERCENT = "percent"
    PERCENT_PLUS_FLAT = "percent_plus_flat"


SALES_CHANNEL_KIND_VALUES: tuple[str, ...] = tuple(m.value for m in SalesChannelKind)
SALES_CHANNEL_FEE_MODEL_VALUES: tuple[str, ...] = tuple(m.value for m in SalesChannelFeeModel)


SALES_CHANNEL_KIND_ENUM = SAEnum(
    SalesChannelKind,
    name="sales_channel_kind",
    values_callable=lambda enum_cls: [m.value for m in enum_cls],
    create_type=False,
)

SALES_CHANNEL_FEE_MODEL_ENUM = SAEnum(
    SalesChannelFeeModel,
    name="sales_channel_fee_model",
    values_callable=lambda enum_cls: [m.value for m in enum_cls],
    create_type=False,
)


class SalesChannel(Base):
    __tablename__ = "sales_channel"
    __table_args__ = (
        Index("ix_sales_channel_is_active", "is_active"),
        Index("ix_sales_channel_kind", "kind"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    slug: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)

    kind: Mapped[SalesChannelKind] = mapped_column(SALES_CHANNEL_KIND_ENUM, nullable=False)
    fee_model: Mapped[SalesChannelFeeModel] = mapped_column(
        SALES_CHANNEL_FEE_MODEL_ENUM, nullable=False
    )

    fee_percent: Mapped[Decimal | None] = mapped_column(Numeric(7, 4), nullable=True)
    fee_flat: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)

    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="1"
    )

    default_revenue_account_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("account.id", ondelete="RESTRICT"), nullable=True
    )
    default_fee_account_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("account.id", ondelete="RESTRICT"), nullable=True
    )
    # Phase 9.9 (#161) — the marketplace clearing / AR account credited
    # by the settlement payout JE. ``None`` until the operator sets it;
    # ``settlements.post`` raises a config error if missing at post time.
    default_clearing_account_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("account.id", ondelete="RESTRICT"), nullable=True
    )

    external_id_format_hint: Mapped[str | None] = mapped_column(Text(), nullable=True)

    # Per-channel tax behavior — POS collects, marketplaces typically
    # don't, wholesale may be exempt. ``NULL`` means the channel
    # doesn't compute tax automatically; callers may still pass a
    # flat ``tax_amount`` to ``checkout()``.
    tax_profile_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("tax_profile.id", ondelete="SET NULL"), nullable=True
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
