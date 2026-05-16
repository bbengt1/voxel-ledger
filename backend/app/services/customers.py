"""Customers service (Phase 7.1, #109).

Owns the ``customer`` aggregate and its ``customer_contact`` children.
The customer is the AR-side subject identity; Phase 6 free-text fields
(``customer_name`` / ``customer_email`` on ``sale`` and ``pos_cart``)
remain as fallback for POS walk-ins but the new ``customer_id`` FK is the
canonical grouping key for invoices, statements, and aging.

Customer numbers are allocated via the race-safe reference allocator
with prefix ``CUST`` (issue #23 / ``app.services.reference_number``).

Account-default fallback chain
------------------------------
``resolve_default_revenue_account`` walks:

    customer.default_revenue_account_id
        -> channel.default_revenue_account_id
        -> settings ``sales_posting.default_ar_account_id``
           (Phase 6.3 control-account setting)

``resolve_default_ar_account`` walks the AR-side chain. Channels don't
carry an AR override today (no column), so the chain skips that hop and
goes straight from customer to the
``sales_posting.default_ar_account_id`` setting. Both functions raise
``MissingDefaultAccountError`` with a precise message when nothing in
the chain resolves.

Snapshot-vs-FK contract on sale / pos_cart
------------------------------------------
The ``customer_name`` / ``customer_email`` snapshot fields on ``sale``
(and the nullable equivalents on ``pos_cart``) are ALWAYS populated.
They are the receipt/list-display source. The new ``customer_id`` FK is
nullable and is populated ONLY when a real customer is selected. The
two are non-conflicting: if both are set, the snapshot is what shows up
on the receipt and the FK is what aggregates AR.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import asc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.events.types import ar as ar_events
from app.models.customer import Customer, CustomerContact, CustomerState
from app.models.sales_channel import SalesChannel
from app.schemas.events import EventCreate
from app.services import event_store
from app.services.reference_number import ReferenceNumberService
from app.services.settings.service import SettingsService

# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class CustomersServiceError(Exception):
    """Base class. Routers map subclasses to 400 unless noted."""


class CustomerNotFoundError(CustomersServiceError):
    """Mapped to 404."""


class CustomerContactNotFoundError(CustomersServiceError):
    """Mapped to 404."""


class DuplicatePrimaryContactError(CustomersServiceError):
    """Only one ``is_primary=True`` per customer."""


class MissingDefaultAccountError(CustomersServiceError):
    """Nothing in the customer -> channel -> settings chain resolved."""


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
            aggregate_type=ar_events.AGGREGATE_TYPE_CUSTOMER,
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
    if isinstance(value, CustomerState):
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
    raise CustomersServiceError(f"invalid address value: {value!r}")


async def _load(
    session: AsyncSession, customer_id: uuid.UUID, *, with_contacts: bool = True
) -> Customer:
    stmt = select(Customer).where(Customer.id == customer_id)
    if with_contacts:
        stmt = stmt.options(selectinload(Customer.contacts))
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise CustomerNotFoundError(str(customer_id))
    if with_contacts:
        await session.refresh(row, ["contacts"])
    return row


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


async def get(session: AsyncSession, customer_id: uuid.UUID) -> Customer:
    return await _load(session, customer_id)


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
    default_revenue_account_id: uuid.UUID | None = None,
    default_ar_account_id: uuid.UUID | None = None,
    tax_profile_id: uuid.UUID | None = None,
    notes: str | None = None,
    actor_user_id: uuid.UUID | None,
) -> Customer:
    display_name = (display_name or "").strip()
    if not display_name:
        raise CustomersServiceError("display_name is required")

    customer_number = await ReferenceNumberService.allocate("CUST", session=session)

    customer = Customer(
        customer_number=customer_number,
        display_name=display_name,
        legal_name=(legal_name or None),
        primary_email=(primary_email or None),
        phone=(phone or None),
        billing_address=_normalize_address(billing_address),
        shipping_address=_normalize_address(shipping_address),
        payment_terms_days=payment_terms_days,
        default_revenue_account_id=default_revenue_account_id,
        default_ar_account_id=default_ar_account_id,
        tax_profile_id=tax_profile_id,
        notes=notes,
        state=CustomerState.ACTIVE,
    )
    session.add(customer)
    await session.flush()

    await _emit(
        session,
        event_type=ar_events.TYPE_CUSTOMER_CREATED,
        aggregate_id=customer.id,
        payload={
            "customer_id": str(customer.id),
            "customer_number": customer.customer_number,
            "display_name": customer.display_name,
            "legal_name": customer.legal_name,
            "primary_email": customer.primary_email,
            "phone": customer.phone,
            "payment_terms_days": customer.payment_terms_days,
            "default_revenue_account_id": (
                str(default_revenue_account_id) if default_revenue_account_id else None
            ),
            "default_ar_account_id": (
                str(default_ar_account_id) if default_ar_account_id else None
            ),
            "tax_profile_id": str(tax_profile_id) if tax_profile_id else None,
            "state": customer.state.value,
        },
        actor_user_id=actor_user_id,
    )
    await session.refresh(customer, ["contacts"])
    return customer


_EDITABLE_FIELDS = (
    "display_name",
    "legal_name",
    "primary_email",
    "phone",
    "billing_address",
    "shipping_address",
    "payment_terms_days",
    "default_revenue_account_id",
    "default_ar_account_id",
    "tax_profile_id",
    "notes",
)


async def update(
    session: AsyncSession,
    *,
    customer_id: uuid.UUID,
    patch: dict[str, Any],
    actor_user_id: uuid.UUID | None,
) -> Customer:
    customer = await _load(session, customer_id)

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
                raise CustomersServiceError("display_name must not be empty")
        elif isinstance(new_value, str):
            stripped = new_value.strip()
            new_value = stripped or None

        current = getattr(customer, field)
        if current == new_value:
            continue
        before[field] = _serialize_field(current)
        after[field] = _serialize_field(new_value)
        setattr(customer, field, new_value)

    if not before:
        return customer

    await session.flush()
    await _emit(
        session,
        event_type=ar_events.TYPE_CUSTOMER_UPDATED,
        aggregate_id=customer.id,
        payload={
            "customer_id": str(customer.id),
            "before": before,
            "after": after,
        },
        actor_user_id=actor_user_id,
    )
    await session.refresh(customer, ["contacts"])
    return customer


async def archive(
    session: AsyncSession, *, customer_id: uuid.UUID, actor_user_id: uuid.UUID | None
) -> Customer:
    customer = await _load(session, customer_id)
    if customer.state == CustomerState.ARCHIVED:
        return customer
    customer.state = CustomerState.ARCHIVED
    await session.flush()
    await _emit(
        session,
        event_type=ar_events.TYPE_CUSTOMER_ARCHIVED,
        aggregate_id=customer.id,
        payload={"customer_id": str(customer.id)},
        actor_user_id=actor_user_id,
    )
    return customer


async def unarchive(
    session: AsyncSession, *, customer_id: uuid.UUID, actor_user_id: uuid.UUID | None
) -> Customer:
    customer = await _load(session, customer_id)
    if customer.state == CustomerState.ACTIVE:
        return customer
    customer.state = CustomerState.ACTIVE
    await session.flush()
    await _emit(
        session,
        event_type=ar_events.TYPE_CUSTOMER_UNARCHIVED,
        aggregate_id=customer.id,
        payload={"customer_id": str(customer.id)},
        actor_user_id=actor_user_id,
    )
    return customer


# ---------------------------------------------------------------------------
# List / search
# ---------------------------------------------------------------------------


async def list_customers(
    session: AsyncSession,
    *,
    state: str | None = None,
    search: str | None = None,
) -> list[Customer]:
    """Return customers sorted by display_name.

    ``search`` does a case-insensitive partial match on ``display_name``
    OR ``customer_number`` so the EntityPicker can hit a single endpoint.
    """
    stmt = select(Customer).options(selectinload(Customer.contacts))
    if state is not None:
        try:
            stmt = stmt.where(Customer.state == CustomerState(state))
        except ValueError as exc:
            raise CustomersServiceError(f"invalid state filter: {state!r}") from exc
    if search:
        like = f"%{search.strip()}%"
        from sqlalchemy import or_

        stmt = stmt.where(
            or_(
                Customer.display_name.ilike(like),
                Customer.customer_number.ilike(like),
            )
        )
    stmt = stmt.order_by(asc(Customer.display_name))
    return list((await session.execute(stmt)).scalars().all())


# ---------------------------------------------------------------------------
# Contacts
# ---------------------------------------------------------------------------


async def _ensure_unique_primary(
    session: AsyncSession,
    *,
    customer_id: uuid.UUID,
    exclude_contact_id: uuid.UUID | None = None,
) -> None:
    stmt = select(CustomerContact.id).where(
        CustomerContact.customer_id == customer_id,
        CustomerContact.is_primary.is_(True),
    )
    if exclude_contact_id is not None:
        stmt = stmt.where(CustomerContact.id != exclude_contact_id)
    if (await session.execute(stmt)).scalar_one_or_none() is not None:
        raise DuplicatePrimaryContactError(
            f"customer {customer_id} already has a primary contact; "
            "demote the existing one before promoting a new one"
        )


async def add_contact(
    session: AsyncSession,
    *,
    customer_id: uuid.UUID,
    name: str,
    email: str | None = None,
    phone: str | None = None,
    role_label: str | None = None,
    is_primary: bool = False,
    actor_user_id: uuid.UUID | None,
) -> CustomerContact:
    # Ensure customer exists.
    await _load(session, customer_id, with_contacts=False)

    name = (name or "").strip()
    if not name:
        raise CustomersServiceError("contact name is required")

    if is_primary:
        await _ensure_unique_primary(session, customer_id=customer_id)

    contact = CustomerContact(
        customer_id=customer_id,
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
        event_type=ar_events.TYPE_CUSTOMER_CONTACT_ADDED,
        aggregate_id=customer_id,
        payload={
            "customer_id": str(customer_id),
            "contact_id": str(contact.id),
            "name": name,
            "role_label": contact.role_label,
            "is_primary": is_primary,
        },
        actor_user_id=actor_user_id,
    )
    return contact


async def _load_contact(session: AsyncSession, contact_id: uuid.UUID) -> CustomerContact:
    stmt = select(CustomerContact).where(CustomerContact.id == contact_id)
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise CustomerContactNotFoundError(str(contact_id))
    return row


_CONTACT_EDITABLE = ("name", "email", "phone", "role_label", "is_primary")


async def update_contact(
    session: AsyncSession,
    *,
    contact_id: uuid.UUID,
    patch: dict[str, Any],
    actor_user_id: uuid.UUID | None,
) -> CustomerContact:
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
                raise CustomersServiceError("contact name must not be empty")
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
            session, customer_id=contact.customer_id, exclude_contact_id=contact.id
        )

    await session.flush()
    await _emit(
        session,
        event_type=ar_events.TYPE_CUSTOMER_CONTACT_UPDATED,
        aggregate_id=contact.customer_id,
        payload={
            "customer_id": str(contact.customer_id),
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
    customer_id = contact.customer_id
    await session.delete(contact)
    await session.flush()
    await _emit(
        session,
        event_type=ar_events.TYPE_CUSTOMER_CONTACT_REMOVED,
        aggregate_id=customer_id,
        payload={
            "customer_id": str(customer_id),
            "contact_id": str(contact_id),
        },
        actor_user_id=actor_user_id,
    )


# ---------------------------------------------------------------------------
# Account fallback chain
# ---------------------------------------------------------------------------


async def resolve_default_revenue_account(
    customer: Customer,
    *,
    channel: SalesChannel | None,
    session: AsyncSession,
) -> uuid.UUID:
    """Walk customer -> channel -> settings for the revenue account."""
    if customer.default_revenue_account_id is not None:
        return customer.default_revenue_account_id
    if channel is not None and channel.default_revenue_account_id is not None:
        return channel.default_revenue_account_id
    # Fall through to the Phase 6.3 sales-posting AR-side setting. The
    # spec calls out either `sales_posting.default_revenue_account_id` or
    # the relevant AR-side setting from Phase 6.3; there is no
    # `default_revenue_account_id` setting registered, so the AR-side
    # control account (`sales_posting.default_ar_account_id`) is the
    # documented fallback.
    value = await SettingsService.get("sales_posting.default_ar_account_id", session=session)
    if value is None:
        raise MissingDefaultAccountError(
            "no default revenue account: customer + channel both unset and "
            "settings 'sales_posting.default_ar_account_id' is unconfigured"
        )
    if isinstance(value, uuid.UUID):
        return value
    return uuid.UUID(str(value))


async def resolve_default_ar_account(
    customer: Customer,
    *,
    channel: SalesChannel | None,  # unused — kept for symmetry/forward-compat
    session: AsyncSession,
) -> uuid.UUID:
    """Walk customer -> (channel — N/A today) -> settings for the AR account.

    Sales channels don't carry an AR-side override column today, so this
    chain skips that hop. Phase 9 may add a per-channel override; when
    it does, this function becomes the single update site.
    """
    if customer.default_ar_account_id is not None:
        return customer.default_ar_account_id
    value = await SettingsService.get("sales_posting.default_ar_account_id", session=session)
    if value is None:
        raise MissingDefaultAccountError(
            "no default AR account: customer unset and settings "
            "'sales_posting.default_ar_account_id' is unconfigured"
        )
    if isinstance(value, uuid.UUID):
        return value
    return uuid.UUID(str(value))


__all__ = [
    "CustomerContactNotFoundError",
    "CustomerNotFoundError",
    "CustomersServiceError",
    "DuplicatePrimaryContactError",
    "MissingDefaultAccountError",
    "add_contact",
    "archive",
    "create",
    "get",
    "list_customers",
    "remove_contact",
    "resolve_default_ar_account",
    "resolve_default_revenue_account",
    "unarchive",
    "update",
    "update_contact",
]
