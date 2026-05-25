"""Deposit slips API (Parity #235)."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_role
from app.core.db import get_session
from app.models.auth import User
from app.models.deposit_slip import DepositSlip
from app.models.payment import Payment
from app.schemas.deposit_slips import (
    DepositSlipBuildRequest,
    DepositSlipResponse,
    UndepositedPaymentResponse,
)
from app.services import deposit_slips as service

router = APIRouter(prefix="/deposit-slips", tags=["deposit-slips"])

_WRITE_ROLES = ("owner", "bookkeeper")
_READ_ROLES = ("owner", "bookkeeper", "viewer")


def _to_slip_response(row: DepositSlip) -> DepositSlipResponse:
    return DepositSlipResponse(
        id=row.id,
        slip_number=row.slip_number,
        bank_account_id=row.bank_account_id,
        deposit_date=row.deposit_date,
        total_amount=row.total_amount,
        state=row.state.value if hasattr(row.state, "value") else row.state,  # type: ignore[arg-type]
        posting_journal_entry_id=row.posting_journal_entry_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _to_undeposited_response(p: Payment) -> UndepositedPaymentResponse:
    return UndepositedPaymentResponse(
        id=p.id,
        payment_number=p.payment_number,
        customer_id=p.customer_id,
        amount=p.amount,
        method=p.method.value if hasattr(p.method, "value") else p.method,  # type: ignore[arg-type]
        received_at=p.received_at,
        reference=p.reference,
    )


@router.get("/undeposited", response_model=list[UndepositedPaymentResponse])
async def list_undeposited(
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(require_role(*_READ_ROLES))],
) -> list[UndepositedPaymentResponse]:
    rows = await service.list_undeposited_payments(session)
    return [_to_undeposited_response(p) for p in rows]


@router.post(
    "",
    response_model=DepositSlipResponse,
    status_code=status.HTTP_201_CREATED,
)
async def build_slip(
    payload: DepositSlipBuildRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role(*_WRITE_ROLES))],
) -> DepositSlipResponse:
    try:
        result = await service.build_slip(
            session,
            payment_ids=list(payload.payment_ids),
            bank_account_id=payload.bank_account_id,
            deposit_date=payload.deposit_date,
            actor_user_id=actor.id,
        )
    except service.DepositSlipServiceError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from None
    slip = await service.get_slip(session, result.slip_id)
    response = _to_slip_response(slip)
    await session.commit()
    return response


@router.get("", response_model=list[DepositSlipResponse])
async def list_deposit_slips(
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(require_role(*_READ_ROLES))],
) -> list[DepositSlipResponse]:
    rows = await service.list_slips(session)
    return [_to_slip_response(r) for r in rows]


@router.get("/{slip_id}", response_model=DepositSlipResponse)
async def get_deposit_slip(
    slip_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(require_role(*_READ_ROLES))],
) -> DepositSlipResponse:
    try:
        slip = await service.get_slip(session, slip_id)
    except service.DepositSlipNotFoundError:
        raise HTTPException(status_code=404, detail="deposit slip not found") from None
    return _to_slip_response(slip)
