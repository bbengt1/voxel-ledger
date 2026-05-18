"""ORM model for the ``expense_category`` table (Phase 8.6, #133).

An expense category is an operator-managed taxonomy on top of the GL
expense accounts. Each category resolves to a *default expense account*
(must be ``account.type='expense'`` — enforced at the service layer, no
DB constraint). Bill lines may reference a category, and at issue time
the bill-posting chain consults the category's default account before
falling back to the vendor default or the AP settings.

Hierarchy
---------
Categories support one level of nesting via the nullable self-FK
``parent_id``. A category may have a parent, but the parent must itself
be a root (``parent.parent_id IS NULL``) — there is no DB constraint
enforcing this; the service layer rejects deeper trees explicitly.

PII rule
--------
``notes`` is a free-form operator field and MUST NEVER be whitelisted
into audit excerpts (see ``app/projections/audit/excerpts.py``).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class ExpenseCategory(Base):
    __tablename__ = "expense_category"
    __table_args__ = (
        Index("ix_expense_category_parent_id", "parent_id"),
        Index("ix_expense_category_is_active", "is_active"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)

    default_expense_account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("account.id", ondelete="RESTRICT"), nullable=False
    )

    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("expense_category.id", ondelete="RESTRICT"), nullable=True
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="1"
    )

    notes: Mapped[str | None] = mapped_column(Text(), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    parent: Mapped[ExpenseCategory | None] = relationship(
        "ExpenseCategory",
        remote_side="ExpenseCategory.id",
    )
