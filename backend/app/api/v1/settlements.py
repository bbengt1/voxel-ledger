"""Settlements endpoints (Phase 9.8, #160).

Thin layer over ``app.services.settlement_imports``. Owner + bookkeeper
write (import + cancel); owner + bookkeeper + sales + viewer read.

``POST /api/v1/settlements`` is a multipart upload modeled after the
Phase 8.9 bank-imports endpoint.
"""

from __future__ import annotations

import json
import uuid
from datetime import date
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_role
from app.core.db import get_session
from app.models.auth import User
from app.models.settlement import Settlement, SettlementLine
from app.schemas.settlements import (
    SettlementLineListResponse,
    SettlementLineResponse,
    SettlementListResponse,
    SettlementResponse,
    SettlementWithLinesResponse,
)
from app.services import settlement_imports as service

router = APIRouter(prefix="/settlements", tags=["settlements"])


def _map_error(exc: Exception) -> HTTPException:
    if isinstance(exc, service.SettlementNotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="settlement not found")
    if isinstance(exc, service.InvalidSettlementStateError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, service.InvalidSettlementFileError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, service.SettlementsServiceError):
        return HTTPException(status_code=400, detail=str(exc))
    raise exc


def _settlement_to_response(row: Settlement) -> SettlementResponse:
    return SettlementResponse(
        id=row.id,
        settlement_number=row.settlement_number,
        channel_id=row.channel_id,
        period_start=row.period_start,
        period_end=row.period_end,
        gross_amount=row.gross_amount,
        fee_amount=row.fee_amount,
        refund_amount=row.refund_amount,
        adjustment_amount=row.adjustment_amount,
        payout_amount=row.payout_amount,
        payout_account_id=row.payout_account_id,
        filename=row.filename,
        imported_at=row.imported_at,
        imported_by_user_id=row.imported_by_user_id,
        state=row.state.value if hasattr(row.state, "value") else str(row.state),
        posting_journal_entry_id=row.posting_journal_entry_id,
        notes=row.notes,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _line_to_response(row: SettlementLine) -> SettlementLineResponse:
    return SettlementLineResponse(
        id=row.id,
        settlement_id=row.settlement_id,
        line_number=row.line_number,
        line_kind=row.line_kind.value if hasattr(row.line_kind, "value") else str(row.line_kind),
        occurred_on=row.occurred_on,
        description=row.description,
        external_order_id=row.external_order_id,
        external_txn_id=row.external_txn_id,
        amount=row.amount,
        state=row.state.value if hasattr(row.state, "value") else str(row.state),
        matched_sale_id=row.matched_sale_id,
        matched_refund_id=row.matched_refund_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.post("", response_model=SettlementResponse, status_code=status.HTTP_201_CREATED)
async def import_settlement(
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role("owner", "bookkeeper"))],
    channel_id: Annotated[uuid.UUID, Form()],
    format_kind: Annotated[str, Form()],
    period_start: Annotated[date, Form()],
    period_end: Annotated[date, Form()],
    payout_account_id: Annotated[uuid.UUID, Form()],
    file: Annotated[UploadFile, File()],
    column_map: Annotated[str | None, Form()] = None,
) -> SettlementResponse:
    content = await file.read()
    parsed_map = None
    if column_map:
        try:
            parsed_map = json.loads(column_map)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail=f"invalid column_map JSON: {exc}") from None
        if not isinstance(parsed_map, dict):
            raise HTTPException(status_code=400, detail="column_map must be a JSON object")
    try:
        row = await service.import_file(
            session=session,
            channel_id=channel_id,
            file_bytes=content,
            filename=file.filename or "upload.csv",
            format_kind=format_kind,
            period_start=period_start,
            period_end=period_end,
            payout_account_id=payout_account_id,
            actor_user_id=actor.id,
            column_map=parsed_map,
        )
    except Exception as exc:
        await session.rollback()
        raise _map_error(exc) from None
    await session.refresh(row, ["created_at", "updated_at", "imported_at"])
    await session.commit()
    return _settlement_to_response(row)


@router.get("", response_model=SettlementListResponse)
async def list_settlements(
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(require_role("owner", "bookkeeper", "sales", "viewer"))],
    channel_id: Annotated[uuid.UUID | None, Query()] = None,
    state: Annotated[str | None, Query()] = None,
    period_start: Annotated[date | None, Query()] = None,
    period_end: Annotated[date | None, Query()] = None,
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> SettlementListResponse:
    try:
        rows, next_cursor = await service.list_settlements(
            session,
            channel_id=channel_id,
            state=state,
            period_start=period_start,
            period_end=period_end,
            limit=limit,
            cursor=cursor,
        )
    except Exception as exc:
        raise _map_error(exc) from None
    return SettlementListResponse(
        items=[_settlement_to_response(r) for r in rows], next_cursor=next_cursor
    )


@router.get("/{settlement_id}", response_model=SettlementWithLinesResponse)
async def get_settlement(
    settlement_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(require_role("owner", "bookkeeper", "sales", "viewer"))],
) -> SettlementWithLinesResponse:
    try:
        row = await service.get(session, settlement_id)
        lines, _ = await service.list_lines(session, settlement_id=settlement_id, limit=10_000)
    except Exception as exc:
        raise _map_error(exc) from None
    return SettlementWithLinesResponse(
        settlement=_settlement_to_response(row),
        lines=[_line_to_response(line) for line in lines],
    )


@router.get("/{settlement_id}/lines", response_model=SettlementLineListResponse)
async def list_settlement_lines(
    settlement_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(require_role("owner", "bookkeeper", "sales", "viewer"))],
    state: Annotated[str | None, Query()] = None,
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
) -> SettlementLineListResponse:
    try:
        # Ensure the settlement exists so the list response can 404 cleanly.
        await service.get(session, settlement_id)
        rows, next_cursor = await service.list_lines(
            session,
            settlement_id=settlement_id,
            state=state,
            limit=limit,
            cursor=cursor,
        )
    except Exception as exc:
        raise _map_error(exc) from None
    return SettlementLineListResponse(
        items=[_line_to_response(r) for r in rows], next_cursor=next_cursor
    )


@router.post("/{settlement_id}/cancel", response_model=SettlementResponse)
async def cancel_settlement(
    settlement_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role("owner", "bookkeeper"))],
) -> SettlementResponse:
    try:
        row = await service.cancel(
            session=session, settlement_id=settlement_id, actor_user_id=actor.id
        )
    except Exception as exc:
        await session.rollback()
        raise _map_error(exc) from None
    await session.refresh(row, ["created_at", "updated_at"])
    await session.commit()
    return _settlement_to_response(row)
