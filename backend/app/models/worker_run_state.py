"""ORM model for ``worker_run_state`` (Issue #220).

Per-job durable record of the last cron run. Written by the
``run_job`` wrapper in ``app/workers/registry.py`` on entry
(``running``), on success (``ok`` + counters), and on failure
(``failed`` + error message). Read by the Control Center's
``failed_jobs`` tile and the new ``/api/v1/admin/workers``
endpoint.
"""

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import (
    DateTime,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class WorkerRunStatus(enum.StrEnum):
    OK = "ok"
    FAILED = "failed"
    RUNNING = "running"


WORKER_RUN_STATUS_VALUES: tuple[str, ...] = tuple(m.value for m in WorkerRunStatus)


WORKER_RUN_STATUS_ENUM = SAEnum(
    WorkerRunStatus,
    name="worker_run_status",
    values_callable=lambda enum_cls: [m.value for m in enum_cls],
    create_type=False,
)


class WorkerRunState(Base):
    __tablename__ = "worker_run_state"
    __table_args__ = (
        Index(
            "ix_worker_run_state_status_finished",
            "last_status",
            "last_finished_at",
        ),
    )

    job_name: Mapped[str] = mapped_column(String(128), primary_key=True)
    last_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_status: Mapped[WorkerRunStatus | None] = mapped_column(
        WORKER_RUN_STATUS_ENUM, nullable=True
    )
    last_error: Mapped[str | None] = mapped_column(Text(), nullable=True)
    last_processed: Mapped[int] = mapped_column(
        Integer(), nullable=False, default=0, server_default="0"
    )
    last_duration_ms: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


__all__ = [
    "WORKER_RUN_STATUS_VALUES",
    "WorkerRunState",
    "WorkerRunStatus",
]
