"""ORM model for the ``camera`` table (Phase 5.1).

A camera is a 1:1 sibling of a ``printer`` row — the
``UNIQUE(printer_id)`` constraint enforces "at most one camera config per
printer". ``ON DELETE CASCADE`` keeps the camera row in lockstep with
its parent printer.

``kind`` is a PG enum (``camera_kind``). On SQLite the same ``SAEnum``
renders as ``VARCHAR + CHECK``.

``password_secret`` is an opaque secret. It is NEVER serialized into a
response, event payload, or audit excerpt — the service layer substitutes
the sentinel ``"***"`` for it everywhere.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Text, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class CameraKind(enum.StrEnum):
    WYZE = "wyze"
    RTSP = "rtsp"
    GO2RTC = "go2rtc"
    OTHER = "other"


CAMERA_KIND_VALUES: tuple[str, ...] = tuple(m.value for m in CameraKind)


CAMERA_KIND_ENUM = SAEnum(
    CameraKind,
    name="camera_kind",
    values_callable=lambda enum_cls: [member.value for member in enum_cls],
)


class Camera(Base):
    __tablename__ = "camera"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    printer_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("printer.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )

    kind: Mapped[CameraKind] = mapped_column(CAMERA_KIND_ENUM, nullable=False)
    snapshot_url: Mapped[str] = mapped_column(Text(), nullable=False)
    username: Mapped[str | None] = mapped_column(Text(), nullable=True)
    # SECRET — never echoed to clients/events/excerpts.
    password_secret: Mapped[str | None] = mapped_column(Text(), nullable=True)

    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="1"
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
