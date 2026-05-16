"""Customers API (Phase 7.1, #109).

Thin layer over ``app.services.customers``. Owner + bookkeeper + sales
write; owner + bookkeeper + sales + viewer read. Contacts are a nested
resource under ``/api/v1/customers/{id}/contacts``.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_role
from app.core.db import get_session
from app.models.auth import User
from app.models.customer import Customer, CustomerContact
from app.schemas.customers import (
    CustomerAddress,
    CustomerContactCreate,
    CustomerContactResponse,
    CustomerContactUpdate,
    CustomerCreate,
    CustomerListResponse,
    CustomerResponse,
    CustomerUpdate,
)
from app.services import customers as customers_service

router = APIRouter(prefix="/customers", tags=["customers"])


def _contact_to_response(c: CustomerContact) -> CustomerContactResponse:
    return CustomerContactResponse(
        id=c.id,
        customer_id=c.customer_id,
        name=c.name,
        email=c.email,
        phone=c.phone,
        role_label=c.role_label,
        is_primary=c.is_primary,
        created_at=c.created_at,
        updated_at=c.updated_at,
    )


def _to_response(customer: Customer) -> CustomerResponse:
    billing = CustomerAddress(**customer.billing_address) if customer.billing_address else None
    shipping = CustomerAddress(**customer.shipping_address) if customer.shipping_address else None
    return CustomerResponse(
        id=customer.id,
        customer_number=customer.customer_number,
        display_name=customer.display_name,
        legal_name=customer.legal_name,
        primary_email=customer.primary_email,
        phone=customer.phone,
        billing_address=billing,
        shipping_address=shipping,
        payment_terms_days=customer.payment_terms_days,
        default_revenue_account_id=customer.default_revenue_account_id,
        default_ar_account_id=customer.default_ar_account_id,
        tax_profile_id=customer.tax_profile_id,
        notes=customer.notes,
        state=customer.state.value,  # type: ignore[arg-type]
        created_at=customer.created_at,
        updated_at=customer.updated_at,
        contacts=[_contact_to_response(c) for c in (customer.contacts or [])],
    )


def _map_error(exc: Exception) -> HTTPException:
    if isinstance(exc, customers_service.CustomerNotFoundError):
        return HTTPException(status_code=404, detail="customer not found")
    if isinstance(exc, customers_service.CustomerContactNotFoundError):
        return HTTPException(status_code=404, detail="contact not found")
    if isinstance(exc, customers_service.DuplicatePrimaryContactError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, customers_service.MissingDefaultAccountError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, customers_service.CustomersServiceError):
        return HTTPException(status_code=400, detail=str(exc))
    raise exc


_WRITE_ROLES = ("owner", "bookkeeper", "sales")
_READ_ROLES = ("owner", "bookkeeper", "sales", "viewer")


@router.post("", response_model=CustomerResponse, status_code=status.HTTP_201_CREATED)
async def create_customer(
    payload: CustomerCreate,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role(*_WRITE_ROLES))],
) -> CustomerResponse:
    try:
        customer = await customers_service.create(
            session,
            display_name=payload.display_name,
            legal_name=payload.legal_name,
            primary_email=payload.primary_email,
            phone=payload.phone,
            billing_address=payload.billing_address,
            shipping_address=payload.shipping_address,
            payment_terms_days=payload.payment_terms_days,
            default_revenue_account_id=payload.default_revenue_account_id,
            default_ar_account_id=payload.default_ar_account_id,
            tax_profile_id=payload.tax_profile_id,
            notes=payload.notes,
            actor_user_id=actor.id,
        )
    except Exception as exc:
        await session.rollback()
        raise _map_error(exc) from None
    await session.refresh(customer, ["created_at", "updated_at"])
    await session.commit()
    return _to_response(customer)


@router.get("", response_model=CustomerListResponse)
async def list_customers(
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(require_role(*_READ_ROLES))],
    state: Annotated[str | None, Query()] = None,
    search: Annotated[str | None, Query()] = None,
) -> CustomerListResponse:
    try:
        rows = await customers_service.list_customers(session, state=state, search=search)
    except Exception as exc:
        raise _map_error(exc) from None
    return CustomerListResponse(items=[_to_response(c) for c in rows])


@router.get("/{customer_id}", response_model=CustomerResponse)
async def get_customer(
    customer_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(require_role(*_READ_ROLES))],
) -> CustomerResponse:
    try:
        customer = await customers_service.get(session, customer_id)
    except Exception as exc:
        raise _map_error(exc) from None
    return _to_response(customer)


@router.patch("/{customer_id}", response_model=CustomerResponse)
async def update_customer(
    customer_id: uuid.UUID,
    payload: CustomerUpdate,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role(*_WRITE_ROLES))],
) -> CustomerResponse:
    patch = payload.model_dump(exclude_unset=True)
    try:
        customer = await customers_service.update(
            session, customer_id=customer_id, patch=patch, actor_user_id=actor.id
        )
    except Exception as exc:
        await session.rollback()
        raise _map_error(exc) from None
    await session.refresh(customer, ["created_at", "updated_at"])
    await session.commit()
    return _to_response(customer)


@router.post("/{customer_id}/archive", response_model=CustomerResponse)
async def archive_customer(
    customer_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role(*_WRITE_ROLES))],
) -> CustomerResponse:
    try:
        customer = await customers_service.archive(
            session, customer_id=customer_id, actor_user_id=actor.id
        )
    except Exception as exc:
        await session.rollback()
        raise _map_error(exc) from None
    await session.commit()
    customer = await customers_service.get(session, customer_id)
    return _to_response(customer)


@router.post("/{customer_id}/unarchive", response_model=CustomerResponse)
async def unarchive_customer(
    customer_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role(*_WRITE_ROLES))],
) -> CustomerResponse:
    try:
        customer = await customers_service.unarchive(
            session, customer_id=customer_id, actor_user_id=actor.id
        )
    except Exception as exc:
        await session.rollback()
        raise _map_error(exc) from None
    await session.commit()
    customer = await customers_service.get(session, customer_id)
    return _to_response(customer)


# --- Contacts (nested) ----------------------------------------------------


@router.post(
    "/{customer_id}/contacts",
    response_model=CustomerContactResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_contact(
    customer_id: uuid.UUID,
    payload: CustomerContactCreate,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role(*_WRITE_ROLES))],
) -> CustomerContactResponse:
    try:
        contact = await customers_service.add_contact(
            session,
            customer_id=customer_id,
            name=payload.name,
            email=payload.email,
            phone=payload.phone,
            role_label=payload.role_label,
            is_primary=payload.is_primary,
            actor_user_id=actor.id,
        )
    except Exception as exc:
        await session.rollback()
        raise _map_error(exc) from None
    await session.refresh(contact, ["created_at", "updated_at"])
    await session.commit()
    return _contact_to_response(contact)


@router.patch(
    "/{customer_id}/contacts/{contact_id}",
    response_model=CustomerContactResponse,
)
async def update_contact(
    customer_id: uuid.UUID,
    contact_id: uuid.UUID,
    payload: CustomerContactUpdate,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role(*_WRITE_ROLES))],
) -> CustomerContactResponse:
    patch = payload.model_dump(exclude_unset=True)
    try:
        contact = await customers_service.update_contact(
            session, contact_id=contact_id, patch=patch, actor_user_id=actor.id
        )
    except Exception as exc:
        await session.rollback()
        raise _map_error(exc) from None
    if contact.customer_id != customer_id:
        raise HTTPException(status_code=404, detail="contact not found")
    await session.refresh(contact, ["created_at", "updated_at"])
    await session.commit()
    return _contact_to_response(contact)


@router.delete("/{customer_id}/contacts/{contact_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_contact(
    customer_id: uuid.UUID,
    contact_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role(*_WRITE_ROLES))],
) -> Response:
    try:
        contact = await customers_service._load_contact(session, contact_id)
        if contact.customer_id != customer_id:
            raise customers_service.CustomerContactNotFoundError(str(contact_id))
        await customers_service.remove_contact(
            session, contact_id=contact_id, actor_user_id=actor.id
        )
    except Exception as exc:
        await session.rollback()
        raise _map_error(exc) from None
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
