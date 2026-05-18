"""ORM model for ``fixed_asset`` (Phase 9.1, #153).

Covers BOTH tangible and intangible assets in a single table — the
``asset_kind`` enum is the discriminator. The acquisition flow (in
``app.services.fixed_assets``) creates a row + posts a JE atomically
inside the same DB transaction.

Per agents.md gotcha #1 the four enums (``fixed_asset_kind``,
``fixed_asset_class``, ``depreciation_method``, ``fixed_asset_state``)
are NOT pre-created in the migration; ``op.create_table`` auto-creates
the PG types via the column dialect hook. Per gotcha #3 the ORM
declares them with ``SAEnum(..., create_type=False,
values_callable=...)``.

The ``posting_journal_entry_id`` FK is nullable: when an asset is
acquired via a bill, no fresh JE is posted (the bill's existing JE
already did Dr Asset / Cr AP). In that case we stamp
``posting_journal_entry_id`` with the bill's
``posting_journal_entry_id`` for traceability.
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
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class FixedAssetKind(enum.StrEnum):
    TANGIBLE = "tangible"
    INTANGIBLE = "intangible"


class FixedAssetClass(enum.StrEnum):
    MACHINE = "machine"
    PRINTER = "printer"
    COMPUTER = "computer"
    FURNITURE = "furniture"
    VEHICLE = "vehicle"
    SOFTWARE = "software"
    INTELLECTUAL_PROPERTY = "intellectual_property"
    OTHER = "other"


class DepreciationMethod(enum.StrEnum):
    STRAIGHT_LINE = "straight_line"
    DECLINING_BALANCE_200 = "declining_balance_200"
    DECLINING_BALANCE_150 = "declining_balance_150"
    NONE = "none"


class FixedAssetState(enum.StrEnum):
    ACTIVE = "active"
    DISPOSED = "disposed"
    WRITTEN_OFF = "written_off"


FIXED_ASSET_KIND_VALUES: tuple[str, ...] = tuple(m.value for m in FixedAssetKind)
FIXED_ASSET_CLASS_VALUES: tuple[str, ...] = tuple(m.value for m in FixedAssetClass)
DEPRECIATION_METHOD_VALUES: tuple[str, ...] = tuple(m.value for m in DepreciationMethod)
FIXED_ASSET_STATE_VALUES: tuple[str, ...] = tuple(m.value for m in FixedAssetState)


FIXED_ASSET_KIND_ENUM = SAEnum(
    FixedAssetKind,
    name="fixed_asset_kind",
    values_callable=lambda enum_cls: [m.value for m in enum_cls],
    create_type=False,
)
FIXED_ASSET_CLASS_ENUM = SAEnum(
    FixedAssetClass,
    name="fixed_asset_class",
    values_callable=lambda enum_cls: [m.value for m in enum_cls],
    create_type=False,
)
DEPRECIATION_METHOD_ENUM = SAEnum(
    DepreciationMethod,
    name="depreciation_method",
    values_callable=lambda enum_cls: [m.value for m in enum_cls],
    create_type=False,
)
FIXED_ASSET_STATE_ENUM = SAEnum(
    FixedAssetState,
    name="fixed_asset_state",
    values_callable=lambda enum_cls: [m.value for m in enum_cls],
    create_type=False,
)


class FixedAsset(Base):
    __tablename__ = "fixed_asset"
    __table_args__ = (
        CheckConstraint("acquisition_cost > 0", name="ck_fixed_asset_cost_positive"),
        CheckConstraint("salvage_value >= 0", name="ck_fixed_asset_salvage_nonneg"),
        CheckConstraint("useful_life_months > 0", name="ck_fixed_asset_life_positive"),
        Index("ix_fixed_asset_kind", "asset_kind"),
        Index("ix_fixed_asset_class", "asset_class"),
        Index("ix_fixed_asset_state", "state"),
        Index("ix_fixed_asset_vendor_id", "vendor_id"),
        Index("ix_fixed_asset_acquisition_bill_id", "acquisition_bill_id"),
        Index("ix_fixed_asset_created_at_id", "created_at", "id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    asset_number: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)

    asset_kind: Mapped[FixedAssetKind] = mapped_column(FIXED_ASSET_KIND_ENUM, nullable=False)
    asset_class: Mapped[FixedAssetClass] = mapped_column(FIXED_ASSET_CLASS_ENUM, nullable=False)

    acquired_on: Mapped[date] = mapped_column(Date(), nullable=False)
    acquisition_cost: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    salvage_value: Mapped[Decimal] = mapped_column(
        Numeric(18, 6), nullable=False, default=Decimal("0"), server_default="0"
    )
    useful_life_months: Mapped[int] = mapped_column(Integer(), nullable=False)

    depreciation_method: Mapped[DepreciationMethod] = mapped_column(
        DEPRECIATION_METHOD_ENUM, nullable=False
    )

    asset_account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("account.id", ondelete="RESTRICT"), nullable=False
    )
    accumulated_depreciation_account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("account.id", ondelete="RESTRICT"), nullable=False
    )
    depreciation_expense_account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("account.id", ondelete="RESTRICT"), nullable=False
    )

    serial_number: Mapped[str | None] = mapped_column(String(128), nullable=True)

    vendor_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("vendor.id", ondelete="RESTRICT"), nullable=True
    )
    acquisition_bill_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("bill.id", ondelete="RESTRICT"), nullable=True
    )

    state: Mapped[FixedAssetState] = mapped_column(
        FIXED_ASSET_STATE_ENUM,
        nullable=False,
        default=FixedAssetState.ACTIVE,
        server_default="active",
    )

    last_depreciated_on: Mapped[date | None] = mapped_column(Date(), nullable=True)

    posting_journal_entry_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("journal_entry.id", ondelete="RESTRICT"), nullable=True
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
