"""ORM model for the ``account`` table (Phase 4.1).

A chart-of-accounts row. ``type`` is a PG enum (``account_type``);
mirrors the ``inventory_location.kind`` pattern (#50) with ``SAEnum(...,
create_type=False)`` so Alembic owns the enum lifecycle.

Hierarchy is self-referencing: ``parent_account_id`` FKs back to
``account.id`` with ``ON DELETE RESTRICT``. Cycle prevention is enforced
at the service layer (see ``app.services.accounts``).

Partial unique index on ``code`` covers active rows only — archived rows
may share a code with a freshly-created active one. Mirrors the supply /
inventory-location convention.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text, func, text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class AccountType(enum.StrEnum):
    ASSET = "asset"
    LIABILITY = "liability"
    EQUITY = "equity"
    REVENUE = "revenue"
    EXPENSE = "expense"


ACCOUNT_TYPE_VALUES: tuple[str, ...] = tuple(member.value for member in AccountType)


# Stable PG enum name. ``create_type=False`` so the migration owns
# creation; ORM merely references the existing type at runtime.
ACCOUNT_TYPE_ENUM = SAEnum(
    *ACCOUNT_TYPE_VALUES,
    name="account_type",
    create_type=False,
)


class Account(Base):
    __tablename__ = "account"
    __table_args__ = (
        # Partial unique: only active rows enforce uniqueness on code.
        Index(
            "ux_account_code_active",
            "code",
            unique=True,
            sqlite_where=text("is_archived = 0"),
            postgresql_where=text("is_archived = false"),
        ),
        Index("ix_account_parent_account_id", "parent_account_id"),
        Index("ix_account_type_code", "type", "code"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    type: Mapped[str] = mapped_column(ACCOUNT_TYPE_ENUM, nullable=False)

    parent_account_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("account.id", ondelete="RESTRICT"), nullable=True
    )

    description: Mapped[str | None] = mapped_column(Text(), nullable=True)

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
