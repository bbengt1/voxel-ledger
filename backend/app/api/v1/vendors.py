"""Vendors API (Phase 8.1, #128).

Thin layer over ``app.services.vendors``. Owner + bookkeeper write;
owner + bookkeeper + sales + viewer read. Contacts are a nested
resource under ``/api/v1/vendors/{id}/contacts``.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_role
from app.core.db import get_session
from app.models.auth import User
from app.models.vendor import Vendor, VendorContact
from app.schemas.vendors import (
    VendorAddress,
    VendorContactCreate,
    VendorContactResponse,
    VendorContactUpdate,
    VendorCreate,
    VendorListResponse,
    VendorResponse,
    VendorUpdate,
)
from app.services import vendors as vendors_service

router = APIRouter(prefix="/vendors", tags=["vendors"])


def _contact_to_response(c: VendorContact) -> VendorContactResponse:
    return VendorContactResponse(
        id=c.id,
        vendor_id=c.vendor_id,
        name=c.name,
        email=c.email,
        phone=c.phone,
        role_label=c.role_label,
        is_primary=c.is_primary,
        created_at=c.created_at,
        updated_at=c.updated_at,
    )


def _to_response(vendor: Vendor) -> VendorResponse:
    billing = VendorAddress(**vendor.billing_address) if vendor.billing_address else None
    shipping = VendorAddress(**vendor.shipping_address) if vendor.shipping_address else None
    return VendorResponse(
        id=vendor.id,
        vendor_number=vendor.vendor_number,
        display_name=vendor.display_name,
        legal_name=vendor.legal_name,
        primary_email=vendor.primary_email,
        phone=vendor.phone,
        billing_address=billing,
        shipping_address=shipping,
        payment_terms_days=vendor.payment_terms_days,
        default_expense_account_id=vendor.default_expense_account_id,
        default_ap_account_id=vendor.default_ap_account_id,
        tax_id=vendor.tax_id,
        is_1099_vendor=vendor.is_1099_vendor,
        notes=vendor.notes,
        state=vendor.state.value,  # type: ignore[arg-type]
        created_at=vendor.created_at,
        updated_at=vendor.updated_at,
        contacts=[_contact_to_response(c) for c in (vendor.contacts or [])],
    )


def _map_error(exc: Exception) -> HTTPException:
    if isinstance(exc, vendors_service.VendorNotFoundError):
        return HTTPException(status_code=404, detail="vendor not found")
    if isinstance(exc, vendors_service.VendorContactNotFoundError):
        return HTTPException(status_code=404, detail="contact not found")
    if isinstance(exc, vendors_service.DuplicatePrimaryContactError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, vendors_service.VendorsServiceError):
        return HTTPException(status_code=400, detail=str(exc))
    raise exc


_WRITE_ROLES = ("owner", "bookkeeper")
_READ_ROLES = ("owner", "bookkeeper", "sales", "viewer")


@router.post("", response_model=VendorResponse, status_code=status.HTTP_201_CREATED)
async def create_vendor(
    payload: VendorCreate,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role(*_WRITE_ROLES))],
) -> VendorResponse:
    try:
        vendor = await vendors_service.create(
            session,
            display_name=payload.display_name,
            legal_name=payload.legal_name,
            primary_email=payload.primary_email,
            phone=payload.phone,
            billing_address=payload.billing_address,
            shipping_address=payload.shipping_address,
            payment_terms_days=payload.payment_terms_days,
            default_expense_account_id=payload.default_expense_account_id,
            default_ap_account_id=payload.default_ap_account_id,
            tax_id=payload.tax_id,
            is_1099_vendor=payload.is_1099_vendor,
            notes=payload.notes,
            actor_user_id=actor.id,
        )
    except Exception as exc:
        await session.rollback()
        raise _map_error(exc) from None
    await session.refresh(vendor, ["created_at", "updated_at"])
    await session.commit()
    return _to_response(vendor)


@router.get("", response_model=VendorListResponse)
async def list_vendors(
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(require_role(*_READ_ROLES))],
    state: Annotated[str | None, Query()] = None,
    search: Annotated[str | None, Query()] = None,
) -> VendorListResponse:
    try:
        rows = await vendors_service.list_vendors(session, state=state, search=search)
    except Exception as exc:
        raise _map_error(exc) from None
    return VendorListResponse(items=[_to_response(v) for v in rows])


@router.get("/{vendor_id}", response_model=VendorResponse)
async def get_vendor(
    vendor_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(require_role(*_READ_ROLES))],
) -> VendorResponse:
    try:
        vendor = await vendors_service.get(session, vendor_id)
    except Exception as exc:
        raise _map_error(exc) from None
    return _to_response(vendor)


@router.patch("/{vendor_id}", response_model=VendorResponse)
async def update_vendor(
    vendor_id: uuid.UUID,
    payload: VendorUpdate,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role(*_WRITE_ROLES))],
) -> VendorResponse:
    patch = payload.model_dump(exclude_unset=True)
    try:
        vendor = await vendors_service.update(
            session, vendor_id=vendor_id, patch=patch, actor_user_id=actor.id
        )
    except Exception as exc:
        await session.rollback()
        raise _map_error(exc) from None
    await session.refresh(vendor, ["created_at", "updated_at"])
    await session.commit()
    return _to_response(vendor)


@router.post("/{vendor_id}/archive", response_model=VendorResponse)
async def archive_vendor(
    vendor_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role(*_WRITE_ROLES))],
) -> VendorResponse:
    try:
        vendor = await vendors_service.archive(session, vendor_id=vendor_id, actor_user_id=actor.id)
    except Exception as exc:
        await session.rollback()
        raise _map_error(exc) from None
    await session.commit()
    vendor = await vendors_service.get(session, vendor_id)
    return _to_response(vendor)


@router.post("/{vendor_id}/unarchive", response_model=VendorResponse)
async def unarchive_vendor(
    vendor_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role(*_WRITE_ROLES))],
) -> VendorResponse:
    try:
        vendor = await vendors_service.unarchive(
            session, vendor_id=vendor_id, actor_user_id=actor.id
        )
    except Exception as exc:
        await session.rollback()
        raise _map_error(exc) from None
    await session.commit()
    vendor = await vendors_service.get(session, vendor_id)
    return _to_response(vendor)


# --- Contacts (nested) ----------------------------------------------------


@router.post(
    "/{vendor_id}/contacts",
    response_model=VendorContactResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_contact(
    vendor_id: uuid.UUID,
    payload: VendorContactCreate,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role(*_WRITE_ROLES))],
) -> VendorContactResponse:
    try:
        contact = await vendors_service.add_contact(
            session,
            vendor_id=vendor_id,
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
    "/{vendor_id}/contacts/{contact_id}",
    response_model=VendorContactResponse,
)
async def update_contact(
    vendor_id: uuid.UUID,
    contact_id: uuid.UUID,
    payload: VendorContactUpdate,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role(*_WRITE_ROLES))],
) -> VendorContactResponse:
    patch = payload.model_dump(exclude_unset=True)
    try:
        contact = await vendors_service.update_contact(
            session, contact_id=contact_id, patch=patch, actor_user_id=actor.id
        )
    except Exception as exc:
        await session.rollback()
        raise _map_error(exc) from None
    if contact.vendor_id != vendor_id:
        raise HTTPException(status_code=404, detail="contact not found")
    await session.refresh(contact, ["created_at", "updated_at"])
    await session.commit()
    return _contact_to_response(contact)


@router.delete("/{vendor_id}/contacts/{contact_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_contact(
    vendor_id: uuid.UUID,
    contact_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role(*_WRITE_ROLES))],
) -> Response:
    try:
        contact = await vendors_service._load_contact(session, contact_id)
        if contact.vendor_id != vendor_id:
            raise vendors_service.VendorContactNotFoundError(str(contact_id))
        await vendors_service.remove_contact(session, contact_id=contact_id, actor_user_id=actor.id)
    except Exception as exc:
        await session.rollback()
        raise _map_error(exc) from None
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
