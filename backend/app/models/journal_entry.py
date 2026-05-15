"""ORM model for the ``journal_entry`` table (Phase 4.2, #65).

A journal entry is the header of a double-entry posting. Lines live in
the sibling ``journal_line`` table. ``entry_number`` is allocated by the
race-safe ``ReferenceNumberService`` with prefix ``JE``.

Immutability is enforced at the DB level via a PG trigger created in
``0018_journal_entries`` (with a single carve-out: ``is_reversed`` may
flip false → true). The trigger does not exist on SQLite — application
code never mutates these rows anyway.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class JournalEntry(Base):
    __tablename__ = "journal_entry"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    entry_number: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)

    # Operative business date.
    posted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # FK + NOT NULL added in Phase 4.3 (#66). Every posted entry must
    # belong to an open accounting period (service enforces).
    period_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(),
        ForeignKey("accounting_period.id", ondelete="RESTRICT"),
        nullable=False,
    )

    description: Mapped[str] = mapped_column(Text(), nullable=False)

    # Reserved for later phases (e.g. linking back to a sale event that
    # auto-posted the entry).
    source_event_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)

    actor_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("user.id", ondelete="RESTRICT"), nullable=False
    )

    is_reversed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )

    reversal_of_entry_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("journal_entry.id", ondelete="RESTRICT"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    lines: Mapped[list[JournalLine]] = relationship(  # type: ignore[name-defined]
        "JournalLine",
        back_populates="entry",
        order_by="JournalLine.line_number",
        cascade="all, delete-orphan",
    )


# Imported at the bottom so the forward-string in ``relationship`` resolves
# without a circular-import dance.
from app.models.journal_line import JournalLine  # noqa: E402
