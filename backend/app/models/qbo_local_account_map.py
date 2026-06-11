"""Mapping of a local chart-of-accounts ``Account`` → QuickBooks Online Account id.

Phase 3d follow-up (#316, epic #312). Most Phase-3 posting sites resolve their
journal lines through an abstract *role* (see :mod:`app.services.quickbooks.roles`
and :class:`app.models.qbo_account_map.QboAccountMap`). Two sites can't:

* inter-account transfers (``app.services.inter_account_transfers``) and
* the bank auto-matcher (``app.services.bank_auto_matcher``)

post to **arbitrary** chart-of-accounts accounts chosen per-transaction (the two
transfer legs; a matcher rule's debit/credit side). Those have no fixed role, so
this table maps each *specific local account* the operator uses there to the QBO
account it should land in. One row per local account.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class QboLocalAccountMap(Base):
    __tablename__ = "qbo_local_account_map"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    # One row per local account; FK so a deleted account drops its mapping.
    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("account.id", ondelete="CASCADE"), nullable=False, unique=True
    )
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
