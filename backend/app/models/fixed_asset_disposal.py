"""ORM model for ``fixed_asset_disposal`` (Phase 9.4, #156).

One row per disposed asset. Constructed in the same DB transaction as
the JE that clears the asset out of the balance sheet, plus any
``planned`` schedule entries past ``disposed_on`` flipped to
``adjusted``.

Per agents.md gotcha #1 the ``asset_disposal_kind`` enum is NOT
pre-created in the migration; ``op.create_table`` auto-creates the PG
type via the column dialect hook. Per gotcha #3 the ORM declares it
with ``SAEnum(..., create_type=False, values_callable=...)``.
"""

from __future__ import annotations

import enum
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class AssetDisposalKind(enum.StrEnum):
    SALE = "sale"
    SCRAP = "scrap"
    WRITEOFF = "writeoff"
    DONATION = "donation"


ASSET_DISPOSAL_KIND_VALUES: tuple[str, ...] = tuple(m.value for m in AssetDisposalKind)


ASSET_DISPOSAL_KIND_ENUM = SAEnum(
    AssetDisposalKind,
    name="asset_disposal_kind",
    values_callable=lambda enum_cls: [m.value for m in enum_cls],
    create_type=False,
)


class FixedAssetDisposal(Base):
    __tablename__ = "fixed_asset_disposal"
    __table_args__ = (
        CheckConstraint("proceeds_amount >= 0", name="ck_fixed_asset_disposal_proceeds_nonneg"),
        UniqueConstraint("asset_id", name="uq_fixed_asset_disposal_asset"),
        Index("ix_fixed_asset_disposal_asset_id", "asset_id"),
        Index("ix_fixed_asset_disposal_disposed_on", "disposed_on"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    asset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("fixed_asset.id", ondelete="RESTRICT"), nullable=False
    )

    disposed_on: Mapped[date] = mapped_column(Date(), nullable=False)
    disposal_kind: Mapped[AssetDisposalKind] = mapped_column(
        ASSET_DISPOSAL_KIND_ENUM, nullable=False
    )

    proceeds_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 6), nullable=False, default=Decimal("0"), server_default="0"
    )
    proceeds_account_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("account.id", ondelete="RESTRICT"), nullable=True
    )

    gain_loss_account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("account.id", ondelete="RESTRICT"), nullable=False
    )

    book_value_at_disposal: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    accumulated_depreciation_at_disposal: Mapped[Decimal] = mapped_column(
        Numeric(18, 6), nullable=False
    )
    gain_loss_amount: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)

    notes: Mapped[str | None] = mapped_column(Text(), nullable=True)

    posting_journal_entry_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("journal_entry.id", ondelete="SET NULL"), nullable=True
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
