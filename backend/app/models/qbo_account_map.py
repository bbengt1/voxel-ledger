"""Mapping of posting-line ROLE → QuickBooks Online Account id.

Phase 2 (#315, epic #312). When QBO becomes the system of record (Phase 3), each
journal line our posting sites emit must reference a QBO ``Account``. QBO's chart
of accounts is authoritative, so rather than mirror our local chart we map each
abstract *role* (revenue, AR, COGS, inventory, AP, bank, …) to the QBO account
the operator chose. The full role set lives in
:class:`app.services.quickbooks.roles.QBOAccountRole`; this table stores one row
per role that has been mapped.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class QboAccountMap(Base):
    __tablename__ = "qbo_account_map"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    # One row per role; the value is a QBOAccountRole string.
    role: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    qbo_account_id: Mapped[str] = mapped_column(String(64), nullable=False)
    # Cached display name for the admin UI (QBO is authoritative for the id).
    qbo_account_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    updated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("user.id", ondelete="SET NULL"), nullable=True
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
