"""ORM models for ``customer`` + ``customer_contact`` (Phase 7.1, #109).

The customer aggregate is the AR-side subject identity. Phase 6 used
``customer_name`` + ``customer_email`` free-text on ``sale`` rows, which
worked for POS walk-ins but blocks the AR pathway. Phase 7.1 introduces
the real ``customer`` row and backfills a nullable ``customer_id`` FK on
``sale`` + ``pos_cart``.

Both the snapshot fields (``customer_name`` / ``customer_email`` on
``sale``) and the new FK can coexist: the snapshot is always populated
for receipt/list display, and ``customer_id`` is set only when a real
customer is selected.

``state`` is a PG enum (``customer_state``) auto-created by the 0033
migration via ``op.create_table`` per agents.md gotcha #1. The ORM
declares it with ``SAEnum(..., create_type=False)`` per gotcha #3 so PG
comparisons stay typed.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class CustomerState(enum.StrEnum):
    ACTIVE = "active"
    ARCHIVED = "archived"


CUSTOMER_STATE_VALUES: tuple[str, ...] = tuple(m.value for m in CustomerState)


CUSTOMER_STATE_ENUM = SAEnum(
    CustomerState,
    name="customer_state",
    values_callable=lambda enum_cls: [m.value for m in enum_cls],
    create_type=False,
)


class Customer(Base):
    __tablename__ = "customer"
    __table_args__ = (
        Index("ix_customer_state", "state"),
        Index("ix_customer_display_name", "display_name"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    customer_number: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    legal_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    primary_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(64), nullable=True)

    billing_address: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    shipping_address: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    payment_terms_days: Mapped[int] = mapped_column(
        Integer(), nullable=False, default=30, server_default="30"
    )

    default_revenue_account_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("account.id", ondelete="RESTRICT"), nullable=True
    )
    default_ar_account_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("account.id", ondelete="RESTRICT"), nullable=True
    )

    # Phase 9.5 added the FK constraint. The column existed since 7.1
    # as a bare UUID; the 0052 migration adds the FK (Postgres only —
    # SQLite ALTER doesn't support ADD CONSTRAINT for FKs, but the ORM
    # relationship still works in tests).
    tax_profile_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("tax_profile.id", ondelete="SET NULL"), nullable=True
    )

    notes: Mapped[str | None] = mapped_column(Text(), nullable=True)

    state: Mapped[CustomerState] = mapped_column(
        CUSTOMER_STATE_ENUM,
        nullable=False,
        default=CustomerState.ACTIVE,
        server_default="active",
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

    contacts: Mapped[list[CustomerContact]] = relationship(
        "CustomerContact",
        back_populates="customer",
        cascade="all, delete-orphan",
        order_by="CustomerContact.created_at",
    )


class CustomerContact(Base):
    __tablename__ = "customer_contact"
    __table_args__ = (Index("ix_customer_contact_customer_id", "customer_id"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    customer_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("customer.id", ondelete="CASCADE"), nullable=False
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    role_label: Mapped[str | None] = mapped_column(Text(), nullable=True)

    is_primary: Mapped[bool] = mapped_column(
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

    customer: Mapped[Customer] = relationship("Customer", back_populates="contacts")
