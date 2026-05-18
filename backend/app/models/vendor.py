"""ORM models for ``vendor`` + ``vendor_contact`` (Phase 8.1, #128).

The vendor aggregate is the AP-side subject identity, mirroring the
Phase 7.1 ``customer`` row on the AR side. Phase 8.2 will land
``bill`` rows that reference ``vendor.id``; this file is the foundation.

``state`` is a PG enum (``vendor_state``) auto-created by the 0040
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


class VendorState(enum.StrEnum):
    ACTIVE = "active"
    ARCHIVED = "archived"


VENDOR_STATE_VALUES: tuple[str, ...] = tuple(m.value for m in VendorState)


VENDOR_STATE_ENUM = SAEnum(
    VendorState,
    name="vendor_state",
    values_callable=lambda enum_cls: [m.value for m in enum_cls],
    create_type=False,
)


class Vendor(Base):
    __tablename__ = "vendor"
    __table_args__ = (
        Index("ix_vendor_state", "state"),
        Index("ix_vendor_display_name", "display_name"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    vendor_number: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    legal_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    primary_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(64), nullable=True)

    billing_address: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    shipping_address: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    payment_terms_days: Mapped[int] = mapped_column(
        Integer(), nullable=False, default=30, server_default="30"
    )

    default_expense_account_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("account.id", ondelete="RESTRICT"), nullable=True
    )
    default_ap_account_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("account.id", ondelete="RESTRICT"), nullable=True
    )

    tax_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_1099_vendor: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )

    # Phase 9.5 (#157): the tax profile to default for bills under this
    # vendor. Bare nullable FK; resolution falls through to line override.
    tax_profile_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("tax_profile.id", ondelete="SET NULL"), nullable=True
    )

    notes: Mapped[str | None] = mapped_column(Text(), nullable=True)

    state: Mapped[VendorState] = mapped_column(
        VENDOR_STATE_ENUM,
        nullable=False,
        default=VendorState.ACTIVE,
        server_default="active",
    )

    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("user.id", ondelete="RESTRICT"), nullable=True
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

    contacts: Mapped[list[VendorContact]] = relationship(
        "VendorContact",
        back_populates="vendor",
        cascade="all, delete-orphan",
        order_by="VendorContact.created_at",
    )


class VendorContact(Base):
    __tablename__ = "vendor_contact"
    __table_args__ = (Index("ix_vendor_contact_vendor_id", "vendor_id"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    vendor_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("vendor.id", ondelete="CASCADE"), nullable=False
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

    vendor: Mapped[Vendor] = relationship("Vendor", back_populates="contacts")
