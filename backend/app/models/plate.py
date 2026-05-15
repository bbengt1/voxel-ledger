"""ORM model for the ``plate`` table (Phase 5.2, #78).

A plate is one printable build-plate layout belonging to a job. Each
plate produces ``parts_per_set`` finished pieces every time it completes
one run. ``runs_completed`` accumulates per-plate as plate runs are
recorded; pieces produced across a job is the **min** of
``parts_per_set * runs_completed`` over its plates.

``print_grams_by_material`` and ``assigned_printer_ids`` are JSON columns
(JSONB on Postgres, JSON on SQLite). Grams are serialized as Decimal
strings; material IDs and printer IDs as UUID strings — round-trip
through the JSON layer without floats.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base

if TYPE_CHECKING:
    from app.models.job import Job


JSON_VARIANT = JSON().with_variant(JSONB(), "postgresql")


class Plate(Base):
    __tablename__ = "plate"
    __table_args__ = (
        CheckConstraint("parts_per_set > 0", name="ck_plate_parts_per_set_positive"),
        CheckConstraint("print_minutes >= 0", name="ck_plate_print_minutes_nonneg"),
        CheckConstraint(
            "print_hours_setup_minutes >= 0",
            name="ck_plate_print_hours_setup_minutes_nonneg",
        ),
        CheckConstraint("runs_completed >= 0", name="ck_plate_runs_completed_nonneg"),
        UniqueConstraint("job_id", "plate_number", name="uq_plate_job_id_plate_number"),
        Index("ix_plate_job_id", "job_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("job.id", ondelete="CASCADE"), nullable=False
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    plate_number: Mapped[int] = mapped_column(Integer(), nullable=False)
    parts_per_set: Mapped[int] = mapped_column(Integer(), nullable=False)
    print_minutes: Mapped[int] = mapped_column(Integer(), nullable=False)

    print_grams_by_material: Mapped[dict] = mapped_column(
        JSON_VARIANT, nullable=False, default=dict, server_default="{}"
    )
    print_hours_setup_minutes: Mapped[int] = mapped_column(
        Integer(), nullable=False, default=0, server_default="0"
    )
    assigned_printer_ids: Mapped[list] = mapped_column(
        JSON_VARIANT, nullable=False, default=list, server_default="[]"
    )
    runs_completed: Mapped[int] = mapped_column(
        Integer(), nullable=False, default=0, server_default="0"
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

    job: Mapped[Job] = relationship("Job", back_populates="plates")
