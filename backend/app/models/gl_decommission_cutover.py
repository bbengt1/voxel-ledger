"""GL decommission cutover declaration (#318, epic #312, Phase 5c).

The hard gate between the additive Phase-5 prep (5a archive, 5b opening-balance
seed) and the destructive steps (5d reports removal, 5e GL-core removal, 5f
table drop). A row here is the owner's explicit, recorded declaration that the
cutover preconditions were all green at a point in time:

* the Phase-4 reconciliation gate was clean (``decommission_ready``),
* a balanced GL archive exists for the cutover date (5a), and
* the opening-balance JE is synced to QBO for the same date (5b).

The destructive sub-phases refuse to act unless exactly such a declaration
exists. At most one row is expected (re-declaration is blocked while one
stands); ``readiness_snapshot`` preserves the evidence the decision was made
on, for audit.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Date, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.core.db import Base

_JSON = JSON().with_variant(JSONB(), "postgresql")


class GlDecommissionCutover(Base):
    __tablename__ = "gl_decommission_cutover"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    # The agreed books-handover date: archive + opening-balance JE both close here.
    cutover_date: Mapped[datetime] = mapped_column(Date, nullable=False)
    # The 5a archive manifest this declaration relied on.
    archive_manifest_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("gl_archive_manifest.id", ondelete="RESTRICT"), nullable=False
    )
    # The 5b synced opening-balance outbox row this declaration relied on.
    opening_balance_outbox_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("qbo_sync_outbox.id", ondelete="RESTRICT"), nullable=False
    )
    # Full readiness report at declaration time (audit evidence).
    readiness_snapshot: Mapped[dict] = mapped_column(_JSON, nullable=False)
    declared_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
