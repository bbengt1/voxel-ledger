"""ORM model for the ``build`` table (assembly-line epic #267, Phase 5).

A **Build** assembles N of a finished Product from its Parts + Supplies
(epic decision #2). On completion it consumes the product's ``part`` and
``supply`` on-hand and credits ``product`` on-hand, capturing the
**assembly labor** spent (decision #7). Job completion credits *part*
stock (Phase 4); products only gain stock via a Build.

Lifecycle (decision #3): ``draft`` → ``completed`` | ``cancelled``. Stock
is only consumed/credited at completion, so a draft can be reviewed for
shortfalls before it touches inventory.

``unit_cost_cached`` / ``total_cost_cached`` snapshot the build cost
(parts + supplies + assembly labor) at completion time.
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
    func,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class BuildState(enum.StrEnum):
    DRAFT = "draft"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


BUILD_STATE_VALUES: tuple[str, ...] = tuple(m.value for m in BuildState)
BUILD_STATE_ENUM = SAEnum(
    BuildState,
    name="build_state",
    values_callable=lambda enum_cls: [member.value for member in enum_cls],
    create_type=False,
)


class Build(Base):
    __tablename__ = "build"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_build_quantity_positive"),
        CheckConstraint("assembly_minutes >= 0", name="ck_build_assembly_minutes_nonneg"),
        Index("ix_build_state_created", "state", "created_at"),
        Index("ix_build_product_state", "product_id", "state"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    build_number: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)

    product_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("product.id", ondelete="RESTRICT"),
        nullable=False,
    )

    state: Mapped[BuildState] = mapped_column(
        BUILD_STATE_ENUM,
        nullable=False,
        default=BuildState.DRAFT,
        server_default="draft",
    )

    # Number of finished products to assemble.
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)

    # Operator labor (minutes) to assemble the whole build run. Defaults
    # from the product's configured assembly_minutes x quantity at create
    # time, but is editable so the build can capture actual labor.
    assembly_minutes: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )

    # Where parts/supplies are consumed from and the product is credited.
    # Resolved + frozen at completion; NULL while a draft.
    location_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("inventory_location.id", ondelete="RESTRICT"), nullable=True
    )

    # Cost snapshot taken at completion (parts + supplies + assembly labor).
    unit_cost_cached: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    total_cost_cached: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)

    notes: Mapped[str | None] = mapped_column(Text(), nullable=True)

    actor_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("user.id", ondelete="RESTRICT"),
        nullable=False,
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
