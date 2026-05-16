"""ORM model for ``email_message`` (Phase 7.7, #115).

The outbound-email delivery log. Every email the system sends — quote,
invoice, statement, recurring invoice, password reset, ad-hoc — gets a
row here. The row carries metadata + storage keys for the body and
attachments; the actual body HTML and attachment blobs live in the
generalized file store from Phase 7.3 (:mod:`app.services.files`).

Per agents.md gotcha #1 the ``email_kind`` and ``email_state`` enums are
NOT pre-created in the migration — ``op.create_table`` autocreates them
via the columns' dialect hook. The ORM declares them with
``SAEnum(*VALUES, name=..., create_type=False)``.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    func,
    text,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class EmailKind(enum.StrEnum):
    QUOTE = "quote"
    INVOICE = "invoice"
    STATEMENT = "statement"
    RECURRING_INVOICE = "recurring_invoice"
    PASSWORD_RESET = "password_reset"
    GENERIC = "generic"


class EmailState(enum.StrEnum):
    QUEUED = "queued"
    SENDING = "sending"
    SENT = "sent"
    FAILED = "failed"
    BOUNCED = "bounced"


EMAIL_KIND_VALUES: tuple[str, ...] = tuple(m.value for m in EmailKind)
EMAIL_STATE_VALUES: tuple[str, ...] = tuple(m.value for m in EmailState)


EMAIL_KIND_ENUM = SAEnum(
    EmailKind,
    name="email_kind",
    values_callable=lambda enum_cls: [m.value for m in enum_cls],
    create_type=False,
)

EMAIL_STATE_ENUM = SAEnum(
    EmailState,
    name="email_state",
    values_callable=lambda enum_cls: [m.value for m in enum_cls],
    create_type=False,
)


class EmailMessage(Base):
    """One outbound email + its delivery state.

    The body HTML lives in file storage under ``body_html_storage_key`` —
    keeps the row small and lets us swap to S3 later without touching
    the table. ``attachments_json`` carries a list of
    ``{filename, storage_key}`` entries pointing at the same store.
    """

    __tablename__ = "email_message"
    __table_args__ = (
        Index("ix_email_message_state", "state"),
        Index("ix_email_message_kind", "kind"),
        Index("ix_email_message_subject", "subject_kind", "subject_id"),
        Index("ix_email_message_next_retry_at", "next_retry_at"),
        Index("ix_email_message_created_at", "created_at"),
        Index(
            "uq_email_message_kind_subject",
            "kind",
            "subject_kind",
            "subject_id",
            unique=True,
            sqlite_where=text("subject_id IS NOT NULL"),
            postgresql_where=text("subject_id IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    kind: Mapped[EmailKind] = mapped_column(EMAIL_KIND_ENUM, nullable=False)

    # subject_kind / subject_id identify the upstream aggregate. Indexed
    # so the dispatcher's idempotency check is O(log n).
    subject_kind: Mapped[str | None] = mapped_column(String(64), nullable=True)
    subject_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)

    to_address: Mapped[str] = mapped_column(String(320), nullable=False)
    from_address: Mapped[str] = mapped_column(String(320), nullable=False)
    subject: Mapped[str] = mapped_column(Text(), nullable=False)

    body_html_storage_key: Mapped[str] = mapped_column(Text(), nullable=False)
    attachments_json: Mapped[list[dict] | None] = mapped_column(JSON, nullable=True)

    state: Mapped[EmailState] = mapped_column(
        EMAIL_STATE_ENUM,
        nullable=False,
        default=EmailState.QUEUED,
        server_default="queued",
    )
    attempts: Mapped[int] = mapped_column(Integer(), nullable=False, default=0, server_default="0")
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text(), nullable=True)
    provider_message_id: Mapped[str | None] = mapped_column(Text(), nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
