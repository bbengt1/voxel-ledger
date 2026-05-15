"""ORM model for the ``approval_request`` table (Phase 4.4, #67).

Generic approval queue row. Polymorphic — ``subject_kind`` + ``subject_id``
identify the entity awaiting approval; no FK because consumers vary
(journal entries, refunds, period closes, ...). The state enum is
created by the migration; the ORM references it with
``create_type=False`` per #55.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, Numeric, String, Text, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.core.db import Base


class ApprovalState(enum.StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


APPROVAL_STATE_VALUES: tuple[str, ...] = tuple(m.value for m in ApprovalState)


APPROVAL_STATE_ENUM = SAEnum(
    *APPROVAL_STATE_VALUES,
    name="approval_state",
    create_type=False,
)


# JSONB on Postgres; plain JSON on SQLite.
_JSON_TYPE = JSON().with_variant(JSONB(), "postgresql")


class ApprovalRequest(Base):
    __tablename__ = "approval_request"
    __table_args__ = (
        Index(
            "ix_approval_request_state_requested_at",
            "state",
            "requested_at",
        ),
        Index(
            "ix_approval_request_type_state",
            "request_type",
            "state",
        ),
        Index(
            "ix_approval_request_subject",
            "subject_kind",
            "subject_id",
        ),
        Index(
            "ix_approval_request_requester",
            "requested_by_user_id",
            "requested_at",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    request_type: Mapped[str] = mapped_column(String(128), nullable=False)
    subject_kind: Mapped[str] = mapped_column(String(64), nullable=False)
    subject_id: Mapped[uuid.UUID] = mapped_column(nullable=False)

    requested_by_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("user.id", ondelete="RESTRICT"), nullable=False
    )
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    state: Mapped[str] = mapped_column(
        APPROVAL_STATE_ENUM,
        nullable=False,
        server_default=ApprovalState.PENDING.value,
    )

    decided_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decision_note: Mapped[str | None] = mapped_column(Text(), nullable=True)

    payload: Mapped[dict[str, Any]] = mapped_column(_JSON_TYPE, nullable=False)
    threshold_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)

    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
