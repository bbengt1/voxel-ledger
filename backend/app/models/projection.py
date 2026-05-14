"""ORM models for projection bookkeeping and the test-only read model.

The ``projection_cursor`` table tracks how far each named projection has
advanced through the event log. It is only meaningful during replay
(see ``app.projections.registry`` for the cursor semantics).

``ProjectionTestEvent`` is the toy read model used by the unit and replay
parity tests. It is NOT a business projection.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class ProjectionCursor(Base):
    """One row per named projection handler; tracks replay progress."""

    __tablename__ = "projection_cursor"

    handler_name: Mapped[str] = mapped_column(String(255), primary_key=True)
    last_position: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class ProjectionTestEvent(Base):
    """Toy read model fed by ``test_event_projection``. Test-only.

    Real business projections live alongside their bounded context and
    are introduced in later phases.
    """

    __tablename__ = "projection_test_event"

    event_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
