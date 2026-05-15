"""ORM model for the ``division`` table (Phase 4.5, #68).

A division is an optional second analytical dimension for journal lines —
think "3D Printing", "Consulting", "Wholesale". Every ``journal_line`` may
carry an optional ``division_id`` so reports can slice activity by both
account and division. Budgets (sibling ``budget`` table) are keyed by
``(account, division, period)``.

``code`` follows the partial-unique-when-active convention used elsewhere
(``supply``, ``inventory_location``, ``account``): two archived rows can
share a code with a fresh active one. Service-side check fires first;
the partial unique index is the DB-level backstop.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Index, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Division(Base):
    __tablename__ = "division"
    __table_args__ = (
        Index(
            "ux_division_code_active",
            "code",
            unique=True,
            sqlite_where=text("is_archived = 0"),
            postgresql_where=text("is_archived = false"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[str] = mapped_column(String(32), nullable=False)

    is_archived: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
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
