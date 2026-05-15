"""ORM models for production orders (Phase 5.5, #81).

A production order is an operator-supplied batch of jobs grouped by
customer, due date, or campaign. The order itself is a thin wrapper —
membership lives on ``production_order_job`` with a ``display_order``
column that the UI uses to render the queue board.

``state`` is a PG enum (``production_order_state``) auto-created by the
0025 migration. Per agents.md gotcha #3, the ORM declares it with
``SAEnum(..., create_type=False)`` so PG comparisons stay typed.

The "one active membership per job" invariant is enforced at the service
layer, not via a DB constraint — a partial unique index on
``(job_id) WHERE state='active'`` would force a denormalized state
column onto ``production_order_job`` just to satisfy the constraint, and
the service-level check is simpler to reason about + test.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base

if TYPE_CHECKING:
    from app.models.job import Job


class ProductionOrderState(enum.StrEnum):
    PLANNING = "planning"
    ACTIVE = "active"
    COMPLETED = "completed"
    ARCHIVED = "archived"


PRODUCTION_ORDER_STATE_VALUES: tuple[str, ...] = tuple(m.value for m in ProductionOrderState)


PRODUCTION_ORDER_STATE_ENUM = SAEnum(
    ProductionOrderState,
    name="production_order_state",
    values_callable=lambda enum_cls: [member.value for member in enum_cls],
    create_type=False,
)


class ProductionOrder(Base):
    __tablename__ = "production_order"
    __table_args__ = (
        Index("ix_production_order_state_priority_due", "state", "priority", "due_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    order_number: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)

    state: Mapped[ProductionOrderState] = mapped_column(
        PRODUCTION_ORDER_STATE_ENUM,
        nullable=False,
        default=ProductionOrderState.PLANNING,
        server_default="planning",
    )

    priority: Mapped[int] = mapped_column(Integer(), nullable=False, default=0, server_default="0")
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
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

    jobs: Mapped[list[ProductionOrderJob]] = relationship(
        "ProductionOrderJob",
        back_populates="order",
        cascade="all, delete-orphan",
        order_by="ProductionOrderJob.display_order",
    )


class ProductionOrderJob(Base):
    __tablename__ = "production_order_job"
    __table_args__ = (Index("ix_production_order_job_job_id", "job_id"),)

    production_order_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("production_order.id", ondelete="CASCADE"),
        primary_key=True,
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("job.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    display_order: Mapped[int] = mapped_column(
        Integer(), nullable=False, default=0, server_default="0"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    order: Mapped[ProductionOrder] = relationship("ProductionOrder", back_populates="jobs")
    job: Mapped[Job] = relationship("Job")
