"""Accounts endpoints (Phase 4.1, #64).

Thin layer over ``app.services.accounts``. Routers commit the
transaction, map service-layer errors to HTTP, and gate each route on
role.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_role
from app.core.db import get_session
from app.models.account import Account
from app.models.auth import User
from app.schemas.accounts import (
    AccountCreateRequest,
    AccountListResponse,
    AccountResponse,
    AccountTreeResponse,
    AccountTypeLiteral,
    AccountUpdateRequest,
    ParentChainItem,
)
from app.schemas.accounts import (
    AccountTreeNode as AccountTreeNodeSchema,
)
from app.services import accounts as accounts_service

router = APIRouter(prefix="/accounts", tags=["accounts"])


def _to_response(account: Account, *, parent_chain: list[Account] | None = None) -> AccountResponse:
    return AccountResponse(
        id=account.id,
        code=account.code,
        name=account.name,
        type=account.type,  # type: ignore[arg-type]
        parent_account_id=account.parent_account_id,
        description=account.description,
        is_archived=account.is_archived,
        created_at=account.created_at,
        updated_at=account.updated_at,
        parent_chain=[
            ParentChainItem(
                id=row.id,
                code=row.code,
                name=row.name,
                type=row.type,  # type: ignore[arg-type]
            )
            for row in (parent_chain or [])
        ],
    )


def _to_tree_node(node: accounts_service.AccountTreeNode) -> AccountTreeNodeSchema:
    a = node.account
    return AccountTreeNodeSchema(
        id=a.id,
        code=a.code,
        name=a.name,
        type=a.type,  # type: ignore[arg-type]
        parent_account_id=a.parent_account_id,
        description=a.description,
        is_archived=a.is_archived,
        created_at=a.created_at,
        updated_at=a.updated_at,
        children=[_to_tree_node(child) for child in node.children],
    )


async def _refresh(session: AsyncSession, account: Account) -> None:
    await session.refresh(account, ["created_at", "updated_at"])


def _map_service_error(exc: accounts_service.AccountsServiceError) -> HTTPException:
    if isinstance(exc, accounts_service.AccountNotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="account not found")
    if isinstance(exc, accounts_service.ParentNotFoundError):
        return HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"parent account not found: {exc}",
        )
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.post(
    "",
    response_model=AccountResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_account(
    payload: AccountCreateRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role("owner", "bookkeeper"))],
) -> AccountResponse:
    try:
        account = await accounts_service.create(
            session,
            code=payload.code,
            name=payload.name,
            type=payload.type,
            parent_account_id=payload.parent_account_id,
            description=payload.description,
            actor_user_id=actor.id,
        )
    except accounts_service.AccountsServiceError as exc:
        await session.rollback()
        raise _map_service_error(exc) from None
    await _refresh(session, account)
    await session.commit()
    return _to_response(account)


@router.get("", response_model=AccountListResponse)
async def list_accounts(
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(get_current_user)],
    search: Annotated[str | None, Query()] = None,
    type: Annotated[AccountTypeLiteral | None, Query()] = None,
    is_archived: Annotated[bool | None, Query()] = None,
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> AccountListResponse:
    try:
        page = await accounts_service.list_accounts(
            session,
            search=search,
            type=type,
            is_archived=is_archived,
            cursor=cursor,
            limit=limit,
        )
    except accounts_service.AccountsServiceError as exc:
        raise _map_service_error(exc) from None
    return AccountListResponse(
        items=[_to_response(a) for a in page.items],
        next_cursor=page.next_cursor,
    )


@router.get("/tree", response_model=AccountTreeResponse)
async def get_tree(
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(get_current_user)],
    include_archived: Annotated[bool, Query()] = False,
) -> AccountTreeResponse:
    roots = await accounts_service.tree(session, include_archived=include_archived)
    return AccountTreeResponse(items=[_to_tree_node(n) for n in roots])


@router.get("/{account_id}", response_model=AccountResponse)
async def get_account(
    account_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(get_current_user)],
) -> AccountResponse:
    try:
        bundle = await accounts_service.get_with_chain(session, account_id)
    except accounts_service.AccountsServiceError as exc:
        raise _map_service_error(exc) from None
    return _to_response(bundle.account, parent_chain=bundle.parent_chain)


@router.patch("/{account_id}", response_model=AccountResponse)
async def update_account(
    account_id: uuid.UUID,
    payload: AccountUpdateRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role("owner", "bookkeeper"))],
) -> AccountResponse:
    patch = payload.model_dump(exclude_unset=True)
    try:
        account = await accounts_service.update(
            session,
            account_id=account_id,
            patch=patch,
            actor_user_id=actor.id,
        )
    except accounts_service.AccountsServiceError as exc:
        await session.rollback()
        raise _map_service_error(exc) from None
    await _refresh(session, account)
    await session.commit()
    return _to_response(account)


@router.post("/{account_id}/archive", response_model=AccountResponse)
async def archive_account(
    account_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role("owner"))],
) -> AccountResponse:
    try:
        account = await accounts_service.archive(
            session, account_id=account_id, actor_user_id=actor.id
        )
    except accounts_service.AccountsServiceError as exc:
        await session.rollback()
        raise _map_service_error(exc) from None
    await _refresh(session, account)
    await session.commit()
    return _to_response(account)


@router.post("/{account_id}/unarchive", response_model=AccountResponse)
async def unarchive_account(
    account_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role("owner"))],
) -> AccountResponse:
    try:
        account = await accounts_service.unarchive(
            session, account_id=account_id, actor_user_id=actor.id
        )
    except accounts_service.AccountsServiceError as exc:
        await session.rollback()
        raise _map_service_error(exc) from None
    await _refresh(session, account)
    await session.commit()
    return _to_response(account)
