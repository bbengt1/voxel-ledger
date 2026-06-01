"""Per-user preferences store (#258).

A small key/value table scoped to a user, used for client-side UI
preferences that should follow the user across devices/sessions — e.g.
which columns are visible in a given table
(``table_columns.<tableId>`` → ``{"visible": [...]}``).

Schema-on-read like ``setting``: ``value`` is opaque JSON, validated by
the caller. Composite PK ``(user_id, key)`` so each user owns one row per
preference key. Deleting a user cascades their preferences away.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.core.db import Base

# JSONB on Postgres, plain JSON on SQLite (tests).
JSONType = JSON().with_variant(JSONB(), "postgresql")


class UserPreference(Base):
    """One preference value for one user, keyed by a namespaced string."""

    __tablename__ = "user_preference"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("user.id", ondelete="CASCADE"), primary_key=True
    )
    # Namespaced dotted key, e.g. ``table_columns.products``.
    key: Mapped[str] = mapped_column(String(255), primary_key=True)
    # Opaque JSON-serializable value; the API validates shape per key.
    value: Mapped[object] = mapped_column(JSONType, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
