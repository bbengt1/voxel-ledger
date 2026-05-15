"""ORM model for the ``printer_history_event`` table (Phase 5.4).

A printer_history_event row is written by the lazy printer monitor
whenever it observes a state transition over the Moonraker WS feed
(``print_started``, ``print_completed``, etc.) plus the synthetic
``connected`` / ``disconnected`` transitions it derives from socket
liveness.

``event_kind`` is a PG enum (``printer_event_kind``). On SQLite the
same ``SAEnum`` renders as ``VARCHAR + CHECK``.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, func, text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.core.db import Base


class PrinterEventKind(enum.StrEnum):
    PRINT_STARTED = "print_started"
    PRINT_PAUSED = "print_paused"
    PRINT_RESUMED = "print_resumed"
    PRINT_COMPLETED = "print_completed"
    PRINT_ERRORED = "print_errored"
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"


PRINTER_EVENT_KIND_VALUES: tuple[str, ...] = tuple(m.value for m in PrinterEventKind)


PRINTER_EVENT_KIND_ENUM = SAEnum(
    PrinterEventKind,
    name="printer_event_kind",
    values_callable=lambda enum_cls: [member.value for member in enum_cls],
    create_type=False,
)

# JSONB on Postgres, plain JSON elsewhere (SQLite tests).
_JSON_TYPE = JSON().with_variant(JSONB(), "postgresql")


class PrinterHistoryEvent(Base):
    __tablename__ = "printer_history_event"
    __table_args__ = (
        Index(
            "ix_printer_history_event_printer_occurred",
            "printer_id",
            text("occurred_at DESC"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    printer_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("printer.id", ondelete="CASCADE"),
        nullable=False,
    )
    event_kind: Mapped[PrinterEventKind] = mapped_column(PRINTER_EVENT_KIND_ENUM, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    details: Mapped[dict | None] = mapped_column(_JSON_TYPE, nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
