"""Vendors service (Phase 8.1, #128).

Owns the ``vendor`` aggregate and its ``vendor_contact`` children. The
vendor is the AP-side subject identity, mirroring the Phase 7.1
customer on the AR side. Phase 8.2 will land ``bill`` rows that reference
``vendor.id``.

Vendor numbers are allocated via the race-safe reference allocator
with prefix ``VEND`` (issue #23 / ``app.services.reference_number``).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import asc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.events.types import ap as ap_events
from app.models.vendor import Vendor, VendorContact, VendorState
from app.schemas.events import EventCreate
from app.services import event_store
from app.services.reference_number import ReferenceNumberService

# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class VendorsServiceError(Exception):
    """Base class. Routers map subclasses to 400 unless noted."""


class VendorNotFoundError(VendorsServiceError):
    """Mapped to 404."""


class VendorContactNotFoundError(VendorsServiceError):
    """Mapped to 404."""


class DuplicatePrimaryContactError(VendorsServiceError):
    """Only one ``is_primary=True`` per vendor."""


# ---------------------------------------------------------------------------
# Event emission helper
# ---------------------------------------------------------------------------


async def _emit(
    session: AsyncSession,
    *,
    event_type: str,
    aggregate_id: uuid.UUID,
    payload: dict[str, Any],
    actor_user_id: uuid.UUID | None,
) -> None:
    await event_store.append(
        EventCreate(
            type=event_type,
            aggregate_type=ap_events.AGGREGATE_TYPE_VENDOR,
            aggregate_id=aggregate_id,
            payload=payload,
            occurred_at=datetime.now(UTC),
            correlation_id=uuid.uuid4(),
            actor_user_id=actor_user_id,
        ),
        session=session,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _serialize_field(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, VendorState):
        return value.value
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _normalize_address(value: Any) -> dict | None:
    if value is None:
        return None
    if hasattr(value, "model_dump"):
        return value.model_dump(exclude_none=False)
    if isinstance(value, dict):
        return dict(value)
    raise VendorsServiceError(f"invalid address value: {value!r}")


async def _load(
    session: AsyncSession, vendor_id: uuid.UUID, *, with_contacts: bool = True
) -> Vendor:
    stmt = select(Vendor).where(Vendor.id == vendor_id)
    if with_contacts:
        stmt = stmt.options(selectinload(Vendor.contacts))
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise VendorNotFoundError(str(vendor_id))
    if with_contacts:
        await session.refresh(row, ["contacts"])
    return row


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


async def get(session: AsyncSession, vendor_id: uuid.UUID) -> Vendor:
    return await _load(session, vendor_id)


async def create(
    session: AsyncSession,
    *,
    display_name: str,
    legal_name: str | None = None,
    primary_email: str | None = None,
    phone: str | None = None,
    billing_address: Any | None = None,
    shipping_address: Any | None = None,
    payment_terms_days: int = 30,
    default_expense_account_id: uuid.UUID | None = None,
    default_ap_account_id: uuid.UUID | None = None,
    tax_id: str | None = None,
    is_1099_vendor: bool = False,
    notes: str | None = None,
    actor_user_id: uuid.UUID | None,
) -> Vendor:
    display_name = (display_name or "").strip()
    if not display_name:
        raise VendorsServiceError("display_name is required")

    vendor_number = await ReferenceNumberService.allocate("VEND", session=session)

    vendor = Vendor(
        vendor_number=vendor_number,
        display_name=display_name,
        legal_name=(legal_name or None),
        primary_email=(primary_email or None),
        phone=(phone or None),
        billing_address=_normalize_address(billing_address),
        shipping_address=_normalize_address(shipping_address),
        payment_terms_days=payment_terms_days,
        default_expense_account_id=default_expense_account_id,
        default_ap_account_id=default_ap_account_id,
        tax_id=(tax_id or None),
        is_1099_vendor=is_1099_vendor,
        notes=notes,
        state=VendorState.ACTIVE,
        created_by_user_id=actor_user_id,
    )
    session.add(vendor)
    await session.flush()

    await _emit(
        session,
        event_type=ap_events.TYPE_VENDOR_CREATED,
        aggregate_id=vendor.id,
        payload={
            "vendor_id": str(vendor.id),
            "vendor_number": vendor.vendor_number,
            "display_name": vendor.display_name,
            "legal_name": vendor.legal_name,
            "primary_email": vendor.primary_email,
            "phone": vendor.phone,
            "payment_terms_days": vendor.payment_terms_days,
            "default_expense_account_id": (
                str(default_expense_account_id) if default_expense_account_id else None
            ),
            "default_ap_account_id": (
                str(default_ap_account_id) if default_ap_account_id else None
            ),
            "tax_id": vendor.tax_id,
            "is_1099_vendor": vendor.is_1099_vendor,
            "state": vendor.state.value,
        },
        actor_user_id=actor_user_id,
    )
    await session.refresh(vendor, ["contacts"])
    return vendor


_EDITABLE_FIELDS = (
    "display_name",
    "legal_name",
    "primary_email",
    "phone",
    "billing_address",
    "shipping_address",
    "payment_terms_days",
    "default_expense_account_id",
    "default_ap_account_id",
    "tax_id",
    "is_1099_vendor",
    "notes",
)


async def update(
    session: AsyncSession,
    *,
    vendor_id: uuid.UUID,
    patch: dict[str, Any],
    actor_user_id: uuid.UUID | None,
) -> Vendor:
    vendor = await _load(session, vendor_id)

    before: dict[str, Any] = {}
    after: dict[str, Any] = {}

    for field in _EDITABLE_FIELDS:
        if field not in patch:
            continue
        new_value = patch[field]
        if field in ("billing_address", "shipping_address"):
            new_value = _normalize_address(new_value)
        elif field == "display_name" and new_value is not None:
            new_value = new_value.strip()
            if not new_value:
                raise VendorsServiceError("display_name must not be empty")
        elif field == "is_1099_vendor":
            pass
        elif isinstance(new_value, str):
            stripped = new_value.strip()
            new_value = stripped or None

        current = getattr(vendor, field)
        if current == new_value:
            continue
        before[field] = _serialize_field(current)
        after[field] = _serialize_field(new_value)
        setattr(vendor, field, new_value)

    if not before:
        return vendor

    await session.flush()
    await _emit(
        session,
        event_type=ap_events.TYPE_VENDOR_UPDATED,
        aggregate_id=vendor.id,
        payload={
            "vendor_id": str(vendor.id),
            "before": before,
            "after": after,
        },
        actor_user_id=actor_user_id,
    )
    await session.refresh(vendor, ["contacts"])
    return vendor


async def archive(
    session: AsyncSession, *, vendor_id: uuid.UUID, actor_user_id: uuid.UUID | None
) -> Vendor:
    vendor = await _load(session, vendor_id)
    if vendor.state == VendorState.ARCHIVED:
        return vendor
    vendor.state = VendorState.ARCHIVED
    await session.flush()
    await _emit(
        session,
        event_type=ap_events.TYPE_VENDOR_ARCHIVED,
        aggregate_id=vendor.id,
        payload={"vendor_id": str(vendor.id)},
        actor_user_id=actor_user_id,
    )
    return vendor


async def unarchive(
    session: AsyncSession, *, vendor_id: uuid.UUID, actor_user_id: uuid.UUID | None
) -> Vendor:
    vendor = await _load(session, vendor_id)
    if vendor.state == VendorState.ACTIVE:
        return vendor
    vendor.state = VendorState.ACTIVE
    await session.flush()
    await _emit(
        session,
        event_type=ap_events.TYPE_VENDOR_UNARCHIVED,
        aggregate_id=vendor.id,
        payload={"vendor_id": str(vendor.id)},
        actor_user_id=actor_user_id,
    )
    return vendor


# ---------------------------------------------------------------------------
# List / search
# ---------------------------------------------------------------------------


async def list_vendors(
    session: AsyncSession,
    *,
    state: str | None = None,
    search: str | None = None,
) -> list[Vendor]:
    """Return vendors sorted by display_name.

    ``search`` does a case-insensitive partial match on ``display_name``
    OR ``vendor_number`` so the EntityPicker can hit a single endpoint.
    """
    stmt = select(Vendor).options(selectinload(Vendor.contacts))
    if state is not None:
        try:
            stmt = stmt.where(Vendor.state == VendorState(state))
        except ValueError as exc:
            raise VendorsServiceError(f"invalid state filter: {state!r}") from exc
    if search:
        like = f"%{search.strip()}%"
        from sqlalchemy import or_

        stmt = stmt.where(
            or_(
                Vendor.display_name.ilike(like),
                Vendor.vendor_number.ilike(like),
            )
        )
    stmt = stmt.order_by(asc(Vendor.display_name))
    return list((await session.execute(stmt)).scalars().all())


# ---------------------------------------------------------------------------
# Contacts
# ---------------------------------------------------------------------------


async def _ensure_unique_primary(
    session: AsyncSession,
    *,
    vendor_id: uuid.UUID,
    exclude_contact_id: uuid.UUID | None = None,
) -> None:
    stmt = select(VendorContact.id).where(
        VendorContact.vendor_id == vendor_id,
        VendorContact.is_primary.is_(True),
    )
    if exclude_contact_id is not None:
        stmt = stmt.where(VendorContact.id != exclude_contact_id)
    if (await session.execute(stmt)).scalar_one_or_none() is not None:
        raise DuplicatePrimaryContactError(
            f"vendor {vendor_id} already has a primary contact; "
            "demote the existing one before promoting a new one"
        )


async def add_contact(
    session: AsyncSession,
    *,
    vendor_id: uuid.UUID,
    name: str,
    email: str | None = None,
    phone: str | None = None,
    role_label: str | None = None,
    is_primary: bool = False,
    actor_user_id: uuid.UUID | None,
) -> VendorContact:
    # Ensure vendor exists.
    await _load(session, vendor_id, with_contacts=False)

    name = (name or "").strip()
    if not name:
        raise VendorsServiceError("contact name is required")

    if is_primary:
        await _ensure_unique_primary(session, vendor_id=vendor_id)

    contact = VendorContact(
        vendor_id=vendor_id,
        name=name,
        email=(email or None),
        phone=(phone or None),
        role_label=(role_label or None),
        is_primary=is_primary,
    )
    session.add(contact)
    await session.flush()

    await _emit(
        session,
        event_type=ap_events.TYPE_VENDOR_CONTACT_ADDED,
        aggregate_id=vendor_id,
        payload={
            "vendor_id": str(vendor_id),
            "contact_id": str(contact.id),
            "name": name,
            "role_label": contact.role_label,
            "is_primary": is_primary,
        },
        actor_user_id=actor_user_id,
    )
    return contact


async def _load_contact(session: AsyncSession, contact_id: uuid.UUID) -> VendorContact:
    stmt = select(VendorContact).where(VendorContact.id == contact_id)
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise VendorContactNotFoundError(str(contact_id))
    return row


_CONTACT_EDITABLE = ("name", "email", "phone", "role_label", "is_primary")


async def update_contact(
    session: AsyncSession,
    *,
    contact_id: uuid.UUID,
    patch: dict[str, Any],
    actor_user_id: uuid.UUID | None,
) -> VendorContact:
    contact = await _load_contact(session, contact_id)

    before: dict[str, Any] = {}
    after: dict[str, Any] = {}
    for field in _CONTACT_EDITABLE:
        if field not in patch:
            continue
        new_value = patch[field]
        if field == "name" and new_value is not None:
            new_value = new_value.strip()
            if not new_value:
                raise VendorsServiceError("contact name must not be empty")
        elif field != "is_primary" and isinstance(new_value, str):
            stripped = new_value.strip()
            new_value = stripped or None
        current = getattr(contact, field)
        if current == new_value:
            continue
        before[field] = _serialize_field(current)
        after[field] = _serialize_field(new_value)
        setattr(contact, field, new_value)

    if not before:
        return contact

    if after.get("is_primary") is True:
        await _ensure_unique_primary(
            session, vendor_id=contact.vendor_id, exclude_contact_id=contact.id
        )

    await session.flush()
    await _emit(
        session,
        event_type=ap_events.TYPE_VENDOR_CONTACT_UPDATED,
        aggregate_id=contact.vendor_id,
        payload={
            "vendor_id": str(contact.vendor_id),
            "contact_id": str(contact.id),
            "before": before,
            "after": after,
        },
        actor_user_id=actor_user_id,
    )
    return contact


async def remove_contact(
    session: AsyncSession,
    *,
    contact_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
) -> None:
    contact = await _load_contact(session, contact_id)
    vendor_id = contact.vendor_id
    await session.delete(contact)
    await session.flush()
    await _emit(
        session,
        event_type=ap_events.TYPE_VENDOR_CONTACT_REMOVED,
        aggregate_id=vendor_id,
        payload={
            "vendor_id": str(vendor_id),
            "contact_id": str(contact_id),
        },
        actor_user_id=actor_user_id,
    )


__all__ = [
    "DuplicatePrimaryContactError",
    "VendorContactNotFoundError",
    "VendorNotFoundError",
    "VendorsServiceError",
    "add_contact",
    "archive",
    "create",
    "get",
    "list_vendors",
    "remove_contact",
    "unarchive",
    "update",
    "update_contact",
]
