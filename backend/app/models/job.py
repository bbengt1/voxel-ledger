"""ORM model for the ``job`` table (Phase 5.2, #78).

A job represents a production run for a single product. It owns one or
more plates (see ``plate``). Pieces produced = ``min(parts_per_set *
runs_completed)`` across all plates; if any plate has zero runs, pieces
are zero.

``state`` is a PG enum (``job_state``) auto-created by the migration.
The ORM declares it with ``SAEnum(*VALUES, name=..., create_type=False)``
so SQLAlchemy emits the right cast on comparisons.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
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


class JobState(enum.StrEnum):
    DRAFT = "draft"
    QUEUED = "queued"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


JOB_STATE_VALUES: tuple[str, ...] = tuple(m.value for m in JobState)


JOB_STATE_ENUM = SAEnum(
    JobState,
    name="job_state",
    values_callable=lambda enum_cls: [member.value for member in enum_cls],
    create_type=False,
)


class Job(Base):
    __tablename__ = "job"
    __table_args__ = (
        CheckConstraint("quantity_ordered > 0", name="ck_job_quantity_ordered_positive"),
        Index("ix_job_state_priority_due", "state", "priority", "due_at"),
        Index("ix_job_product_state", "product_id", "state"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    job_number: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)

    # Assembly-line epic #267 Phase 4: a job produces a Part. ``product_id``
    # is now nullable (legacy product-jobs; backfilled to a part in Phase 7),
    # and ``part_id`` is the part a new job makes. Exactly one is set.
    product_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("product.id", ondelete="RESTRICT"), nullable=True
    )
    part_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("part.id", ondelete="RESTRICT"), nullable=True
    )
    customer_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)

    state: Mapped[JobState] = mapped_column(
        JOB_STATE_ENUM, nullable=False, default=JobState.DRAFT, server_default="draft"
    )

    quantity_ordered: Mapped[int] = mapped_column(Integer(), nullable=False)
    description: Mapped[str | None] = mapped_column(Text(), nullable=True)
    priority: Mapped[int] = mapped_column(Integer(), nullable=False, default=0, server_default="0")
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text(), nullable=True)

    actor_user_id: Mapped[uuid.UUID] = mapped_column(
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

    plates: Mapped[list[Plate]] = relationship(  # noqa: F821
        "Plate",
        back_populates="job",
        cascade="all, delete-orphan",
        order_by="Plate.plate_number",
    )

    # The Part this job produces (assembly-line epic #267). Eager-loaded so
    # the API response can surface the part's sku/name on every job-fetch
    # path (list/get/create/update/actions) without per-call selectinload.
    part: Mapped[Part | None] = relationship("Part", lazy="selectin")  # noqa: F821
