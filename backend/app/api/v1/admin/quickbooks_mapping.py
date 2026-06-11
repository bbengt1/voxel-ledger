"""Admin endpoints for QBO master-data + account mapping (#315, epic #312).

Owner-only, mounted under ``/api/v1/admin/quickbooks``:

* ``GET  /accounts``       → live list of QBO accounts (to populate the map UI).
* ``GET  /account-map``    → current role→account map + unmapped roles.
* ``PUT  /account-map``    → set role→account mappings.
* ``GET  /local-account-map`` → current local-account→QBO-account map.
* ``PUT  /local-account-map`` → set local-account→QBO-account mappings (for the
  inter-account-transfer + bank-matcher sites, whose legs have no fixed role).
* ``POST /sync/{kind}/{local_id}`` → idempotently upsert a customer/vendor/
  product into QBO (admin-triggered; Phase 3 automates this).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_settings, require_role
from app.core.db import get_session
from app.core.settings import Settings
from app.models.auth import User
from app.services.quickbooks import account_map, local_account_map, master_data
from app.services.quickbooks import oauth as qbo_oauth
from app.services.quickbooks.client import QuickBooksApiError, QuickBooksClient

router = APIRouter(prefix="/quickbooks", tags=["admin-quickbooks"])

_SYNC_DISPATCH = {
    "customer": master_data.upsert_customer,
    "vendor": master_data.upsert_vendor,
    "product": master_data.upsert_product,
}


class QboAccountChoice(BaseModel):
    id: str
    name: str
    account_type: str | None = None
    classification: str | None = None


class AccountMapEntry(BaseModel):
    qbo_account_id: str
    qbo_account_name: str | None = None


class AccountMapResponse(BaseModel):
    roles: list[str]
    mappings: dict[str, AccountMapEntry]
    unmapped: list[str]


class SetAccountMapRequest(BaseModel):
    mappings: dict[str, AccountMapEntry]


class LocalAccountMapEntry(BaseModel):
    qbo_account_id: str
    qbo_account_name: str | None = None


class LocalAccountMapResponse(BaseModel):
    # keyed by local account id (str UUID)
    mappings: dict[str, LocalAccountMapEntry]


class SetLocalAccountMapRequest(BaseModel):
    mappings: dict[str, LocalAccountMapEntry]


class EntityMapResponse(BaseModel):
    local_kind: str
    local_id: uuid.UUID
    qbo_entity_type: str
    qbo_id: str
    sync_token: str | None = None
    last_synced_at: datetime | None = None


def _qbo_http_error(exc: Exception) -> HTTPException:
    """Translate QBO service errors into HTTP responses."""
    if isinstance(exc, qbo_oauth.QuickBooksNotConnectedError):
        return HTTPException(status.HTTP_409_CONFLICT, detail="QuickBooks is not connected")
    if isinstance(exc, account_map.AccountRoleNotMappedError):
        return HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc))
    if isinstance(exc, master_data.MasterDataSyncError):
        return HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, QuickBooksApiError):
        return HTTPException(status.HTTP_502_BAD_GATEWAY, detail=str(exc))
    return HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, detail="quickbooks sync failed")


async def _build_map_response(session: AsyncSession) -> AccountMapResponse:
    mapped = await account_map.get_map(session)
    return AccountMapResponse(
        roles=account_map.all_roles(),
        mappings={k: AccountMapEntry(**v) for k, v in mapped.items()},
        unmapped=await account_map.unmapped_roles(session),
    )


@router.get("/accounts", response_model=list[QboAccountChoice])
async def list_qbo_accounts(
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    _user: Annotated[User, Depends(require_role("owner"))],
) -> list[QboAccountChoice]:
    client = QuickBooksClient(session, settings)
    try:
        accounts = await account_map.list_qbo_accounts(client)
    except (qbo_oauth.QuickBooksNotConnectedError, QuickBooksApiError) as exc:
        raise _qbo_http_error(exc) from exc
    return [QboAccountChoice(**a) for a in accounts if a.get("id")]


@router.get("/account-map", response_model=AccountMapResponse)
async def get_account_map(
    session: Annotated[AsyncSession, Depends(get_session)],
    _user: Annotated[User, Depends(require_role("owner"))],
) -> AccountMapResponse:
    return await _build_map_response(session)


@router.put("/account-map", response_model=AccountMapResponse)
async def put_account_map(
    body: SetAccountMapRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(require_role("owner"))],
) -> AccountMapResponse:
    payload: dict[str, dict[str, Any]] = {
        role: entry.model_dump() for role, entry in body.mappings.items()
    }
    try:
        await account_map.set_mappings(session, payload, actor_user_id=user.id)
    except account_map.UnknownAccountRoleError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    await session.commit()
    return await _build_map_response(session)


async def _build_local_map_response(session: AsyncSession) -> LocalAccountMapResponse:
    mapped = await local_account_map.get_map(session)
    return LocalAccountMapResponse(
        mappings={k: LocalAccountMapEntry(**v) for k, v in mapped.items()}
    )


@router.get("/local-account-map", response_model=LocalAccountMapResponse)
async def get_local_account_map(
    session: Annotated[AsyncSession, Depends(get_session)],
    _user: Annotated[User, Depends(require_role("owner"))],
) -> LocalAccountMapResponse:
    return await _build_local_map_response(session)


@router.put("/local-account-map", response_model=LocalAccountMapResponse)
async def put_local_account_map(
    body: SetLocalAccountMapRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(require_role("owner"))],
) -> LocalAccountMapResponse:
    payload: dict[str, dict[str, Any]] = {
        local_id: entry.model_dump() for local_id, entry in body.mappings.items()
    }
    try:
        await local_account_map.set_mappings(session, payload, actor_user_id=user.id)
    except local_account_map.UnknownLocalAccountError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    await session.commit()
    return await _build_local_map_response(session)


@router.post("/sync/{kind}/{local_id}", response_model=EntityMapResponse)
async def sync_entity(
    kind: str,
    local_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    _user: Annotated[User, Depends(require_role("owner"))],
) -> EntityMapResponse:
    upsert = _SYNC_DISPATCH.get(kind)
    if upsert is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail="kind must be customer, vendor, or product"
        )
    client = QuickBooksClient(session, settings)
    try:
        mapping = await upsert(session, client, local_id)
    except (
        qbo_oauth.QuickBooksNotConnectedError,
        account_map.AccountRoleNotMappedError,
        master_data.MasterDataSyncError,
        QuickBooksApiError,
    ) as exc:
        await session.rollback()
        raise _qbo_http_error(exc) from exc
    await session.commit()
    return EntityMapResponse(
        local_kind=mapping.local_kind,
        local_id=mapping.local_id,
        qbo_entity_type=mapping.qbo_entity_type,
        qbo_id=mapping.qbo_id,
        sync_token=mapping.sync_token,
        last_synced_at=mapping.last_synced_at,
    )
