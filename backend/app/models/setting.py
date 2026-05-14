"""ORM model for the operational settings store (Phase 1.5).

This is the *business / operational* settings table — runtime-editable
key/value pairs owned by the owner role (e.g. cost-engine inputs, POS
padding). It is intentionally separate from ``app.core.settings.Settings``,
which is the deployment-time, env-driven configuration loaded by
pydantic-settings on boot.

The table is typed via schema-on-read: ``value`` is stored as JSONB and
each key has a Pydantic schema in ``app.services.settings.schemas`` that
validates and (de)serializes it. Reading an unknown key raises, so we
never silently return junk.
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


class Setting(Base):
    """A single operational setting, keyed by a namespaced string."""

    __tablename__ = "setting"

    # Namespaced dotted key, e.g. ``cost_engine.labor_rate_per_hour``.
    # 255 is more than we will ever need; keep the column comfortable so
    # we don't have to migrate it later just because someone picked a
    # verbose key.
    key: Mapped[str] = mapped_column(String(255), primary_key=True)

    # Raw JSON-serializable value. The schema registry validates this on
    # read and write — the table is intentionally untyped at the storage
    # layer so we can evolve schemas without DDL churn.
    value: Mapped[object] = mapped_column(JSONType, nullable=False)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Nullable: the seed / migration / startup path may write defaults
    # without a logged-in actor. The FK uses ``SET NULL`` so deleting a
    # user doesn't cascade-destroy the operational history.
    updated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )
