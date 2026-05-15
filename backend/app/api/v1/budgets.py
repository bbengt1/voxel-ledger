"""Budgets endpoints (Phase 4.5, #68).

Thin layer over :class:`app.services.budgets.BudgetsService`. Routers
commit the transaction, map service-layer errors to HTTP, and gate each
route on role.
"""

from __future__ import annotations

import uuid
from typing import Annotated, cast

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_role
from app.core.db import get_session
from app.models.auth import User
from app.schemas.accounts import AccountTypeLiteral
from app.schemas.budgets import (
    BudgetDeleteRequest,
    BudgetListResponse,
    BudgetResponse,
    BudgetUpsertRequest,
    BudgetVarianceResponse,
)
from app.schemas.budgets import (
    BudgetVarianceRow as BudgetVarianceRowSchema,
)
from app.services import budgets as budgets_service
from app.services.budgets import BudgetsService

router = APIRouter(prefix="/accounting/budgets", tags=["budgets"])


def _to_response(row: budgets_service.BudgetRow) -> BudgetResponse:
    return BudgetResponse(
        id=row.id,
        account_id=row.account_id,
        account_code=row.account_code,
        account_name=row.account_name,
        account_type=cast(AccountTypeLiteral, row.account_type),
        division_id=row.division_id,
        division_name=row.division_name,
        division_code=row.division_code,
        period_id=row.period_id,
        amount=row.amount,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _map_error(exc: budgets_service.BudgetsServiceError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.post("", response_model=BudgetResponse)
async def upsert_budget(
    payload: BudgetUpsertRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role("owner", "bookkeeper"))],
) -> BudgetResponse:
    try:
        await BudgetsService.set(
            payload.account_id,
            payload.division_id,
            payload.period_id,
            payload.amount,
            session=session,
            actor_user_id=actor.id,
        )
    except budgets_service.BudgetsServiceError as exc:
        await session.rollback()
        raise _map_error(exc) from None
    rows = await BudgetsService.list(
        session=session,
        period_id=payload.period_id,
        account_id=payload.account_id,
        division_id=payload.division_id,
    )
    # The list helper filters on division_id == X, which on SQLite will
    # also drop NULL-division rows when division_id is None. Re-query
    # explicitly for the null-division case.
    if payload.division_id is None:
        rows = [r for r in rows if r.division_id is None]
    await session.commit()
    # rows always has exactly one entry for this slot post-upsert.
    return _to_response(rows[0])


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def delete_budget(
    payload: BudgetDeleteRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role("owner", "bookkeeper"))],
) -> Response:
    try:
        deleted = await BudgetsService.unset(
            payload.account_id,
            payload.division_id,
            payload.period_id,
            session=session,
            actor_user_id=actor.id,
        )
    except budgets_service.BudgetsServiceError as exc:
        await session.rollback()
        raise _map_error(exc) from None
    if not deleted:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="budget not found")
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("", response_model=BudgetListResponse)
async def list_budgets(
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(require_role("owner", "bookkeeper"))],
    period_id: Annotated[uuid.UUID | None, Query()] = None,
    account_id: Annotated[uuid.UUID | None, Query()] = None,
    division_id: Annotated[uuid.UUID | None, Query()] = None,
) -> BudgetListResponse:
    rows = await BudgetsService.list(
        session=session,
        period_id=period_id,
        account_id=account_id,
        division_id=division_id,
    )
    return BudgetListResponse(items=[_to_response(r) for r in rows])


@router.get("/variance", response_model=BudgetVarianceResponse)
async def variance(
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(require_role("owner", "bookkeeper"))],
    period_id: Annotated[uuid.UUID, Query()],
    account_id: Annotated[uuid.UUID | None, Query()] = None,
    division_id: Annotated[uuid.UUID | None, Query()] = None,
) -> BudgetVarianceResponse:
    try:
        rows = await BudgetsService.variance(
            period_id,
            session=session,
            division_id=division_id,
            account_id=account_id,
        )
    except budgets_service.BudgetsServiceError as exc:
        raise _map_error(exc) from None
    return BudgetVarianceResponse(
        period_id=period_id,
        items=[
            BudgetVarianceRowSchema(
                account_id=r.account_id,
                account_code=r.account_code,
                account_name=r.account_name,
                account_type=cast(AccountTypeLiteral, r.account_type),
                division_id=r.division_id,
                division_name=r.division_name,
                budget_amount=r.budget_amount,
                actual_amount=r.actual_amount,
                variance=r.variance,
                variance_pct=r.variance_pct,
            )
            for r in rows
        ],
    )
