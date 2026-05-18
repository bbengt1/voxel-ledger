"""Expense categories endpoints (Phase 8.6, #133).

Thin layer over ``app.services.expense_categories``. Routers commit the
transaction, map service-layer errors to HTTP, and gate each route on
role. Owner + bookkeeper write; owner + bookkeeper + sales + viewer
read.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_role
from app.core.db import get_session
from app.models.auth import User
from app.models.expense_category import ExpenseCategory
from app.schemas.expense_categories import (
    ExpenseCategoryCreate,
    ExpenseCategoryListResponse,
    ExpenseCategoryResponse,
    ExpenseCategoryUpdate,
)
from app.services import expense_categories as service

router = APIRouter(prefix="/expense-categories", tags=["expense-categories"])


def _to_response(row: ExpenseCategory) -> ExpenseCategoryResponse:
    return ExpenseCategoryResponse(
        id=row.id,
        code=row.code,
        name=row.name,
        default_expense_account_id=row.default_expense_account_id,
        parent_id=row.parent_id,
        is_active=row.is_active,
        notes=row.notes,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _map_error(exc: Exception) -> HTTPException:
    if isinstance(exc, service.ExpenseCategoryNotFoundError):
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="expense category not found"
        )
    if isinstance(exc, service.ExpenseCategoryInUseError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, service.DuplicateExpenseCategoryError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, service.InvalidExpenseCategoryError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, service.ExpenseCategoriesServiceError):
        return HTTPException(status_code=400, detail=str(exc))
    raise exc


@router.post("", response_model=ExpenseCategoryResponse, status_code=status.HTTP_201_CREATED)
async def create_expense_category(
    payload: ExpenseCategoryCreate,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role("owner", "bookkeeper"))],
) -> ExpenseCategoryResponse:
    try:
        row = await service.create(
            session,
            code=payload.code,
            name=payload.name,
            default_expense_account_id=payload.default_expense_account_id,
            parent_id=payload.parent_id,
            notes=payload.notes,
            actor_user_id=actor.id,
        )
    except Exception as exc:
        await session.rollback()
        raise _map_error(exc) from None
    await session.refresh(row, ["created_at", "updated_at"])
    await session.commit()
    return _to_response(row)


@router.get("", response_model=ExpenseCategoryListResponse)
async def list_expense_categories(
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(require_role("owner", "bookkeeper", "sales", "viewer"))],
    active: Annotated[bool | None, Query()] = None,
    search: Annotated[str | None, Query()] = None,
    parent_id: Annotated[uuid.UUID | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
) -> ExpenseCategoryListResponse:
    rows = await service.list_categories(
        session,
        active=active,
        search=search,
        parent_id=parent_id,
        limit=limit,
    )
    return ExpenseCategoryListResponse(items=[_to_response(r) for r in rows])


@router.get("/{category_id}", response_model=ExpenseCategoryResponse)
async def get_expense_category(
    category_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(require_role("owner", "bookkeeper", "sales", "viewer"))],
) -> ExpenseCategoryResponse:
    try:
        row = await service.get(session, category_id)
    except Exception as exc:
        raise _map_error(exc) from None
    return _to_response(row)


@router.patch("/{category_id}", response_model=ExpenseCategoryResponse)
async def update_expense_category(
    category_id: uuid.UUID,
    payload: ExpenseCategoryUpdate,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role("owner", "bookkeeper"))],
) -> ExpenseCategoryResponse:
    patch = payload.model_dump(exclude_unset=True)
    try:
        row = await service.update(
            session, category_id=category_id, patch=patch, actor_user_id=actor.id
        )
    except Exception as exc:
        await session.rollback()
        raise _map_error(exc) from None
    await session.refresh(row, ["created_at", "updated_at"])
    await session.commit()
    return _to_response(row)


@router.post("/{category_id}/archive", response_model=ExpenseCategoryResponse)
async def archive_expense_category(
    category_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role("owner", "bookkeeper"))],
) -> ExpenseCategoryResponse:
    try:
        row = await service.archive(session, category_id=category_id, actor_user_id=actor.id)
    except Exception as exc:
        await session.rollback()
        raise _map_error(exc) from None
    await session.refresh(row, ["created_at", "updated_at"])
    await session.commit()
    return _to_response(row)


@router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_expense_category(
    category_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role("owner", "bookkeeper"))],
) -> None:
    try:
        await service.delete(session, category_id=category_id, actor_user_id=actor.id)
    except Exception as exc:
        await session.rollback()
        raise _map_error(exc) from None
    await session.commit()
