"""ORM model for ``depreciation_schedule_entry`` (Phase 9.2, #154).

A row per month-of-life for each :class:`FixedAsset`. Generated up-front
in the same DB transaction as :func:`app.services.fixed_assets.acquire`;
Phase 9.3's worker walks the planned entries and posts JEs.

Per agents.md gotcha #1 the ``depreciation_entry_state`` enum is NOT
pre-created in the migration. Per gotcha #3 the ORM declares it with
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
    UniqueConstraint,
    func,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class DepreciationEntryState(enum.StrEnum):
    PLANNED = "planned"
    POSTED = "posted"
    ADJUSTED = "adjusted"


DEPRECIATION_ENTRY_STATE_VALUES: tuple[str, ...] = tuple(m.value for m in DepreciationEntryState)


DEPRECIATION_ENTRY_STATE_ENUM = SAEnum(
    DepreciationEntryState,
    name="depreciation_entry_state",
    values_callable=lambda enum_cls: [m.value for m in enum_cls],
    create_type=False,
)


class DepreciationScheduleEntry(Base):
    __tablename__ = "depreciation_schedule_entry"
    __table_args__ = (
        UniqueConstraint("asset_id", "period_index", name="uq_depreciation_entry_asset_period"),
        Index(
            "ix_depreciation_entry_asset_period_end",
            "asset_id",
            "period_end",
        ),
        Index(
            "ix_depreciation_entry_state_period_end",
            "state",
            "period_end",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    asset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("fixed_asset.id", ondelete="CASCADE"), nullable=False
    )
    period_index: Mapped[int] = mapped_column(Integer(), nullable=False)
    period_end: Mapped[date] = mapped_column(Date(), nullable=False)

    opening_book_value: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    depreciation_amount: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    closing_book_value: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)

    state: Mapped[DepreciationEntryState] = mapped_column(
        DEPRECIATION_ENTRY_STATE_ENUM,
        nullable=False,
        default=DepreciationEntryState.PLANNED,
        server_default="planned",
    )

    journal_entry_id: Mapped[uuid.UUID | None] = mapped_column(
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
