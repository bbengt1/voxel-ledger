"""Banking endpoints (Phase 8.9, #136).

Thin layer over ``app.services.bank_imports``. Owner + bookkeeper write
(mappings + import); owner + bookkeeper + sales + viewer read.

The ``POST /api/v1/bank-imports`` endpoint accepts a multipart upload
(``file`` + ``account_id`` + optional ``mapping_id``). OFX uploads can
skip the mapping; CSV uploads must reference one.
"""

from __future__ import annotations

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
from app.models.bank import BankImportMapping, BankImportRun, BankTransaction
from app.schemas.banking import (
    BankImportMappingCreate,
    BankImportMappingListResponse,
    BankImportMappingResponse,
    BankImportMappingUpdate,
    BankImportRunResponse,
    BankTransactionListResponse,
    BankTransactionResponse,
)
from app.services import bank_imports as service

mappings_router = APIRouter(prefix="/bank-import-mappings", tags=["banking"])
imports_router = APIRouter(prefix="/bank-imports", tags=["banking"])
transactions_router = APIRouter(prefix="/bank-transactions", tags=["banking"])


def _map_error(exc: Exception) -> HTTPException:
    if isinstance(exc, service.BankImportMappingNotFoundError):
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="bank import mapping not found"
        )
    if isinstance(exc, service.BankImportRunNotFoundError):
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="bank import run not found"
        )
    if isinstance(exc, service.DuplicateBankImportMappingError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, service.InvalidBankImportMappingError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, service.InvalidBankImportFileError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, service.BankImportsServiceError):
        return HTTPException(status_code=400, detail=str(exc))
    raise exc


def _mapping_to_response(row: BankImportMapping) -> BankImportMappingResponse:
    return BankImportMappingResponse(
        id=row.id,
        name=row.name,
        account_id=row.account_id,
        file_kind=row.file_kind.value if hasattr(row.file_kind, "value") else str(row.file_kind),
        column_map=dict(row.column_map or {}),
        date_format=row.date_format,
        delimiter=row.delimiter,
        has_header=row.has_header,
        encoding=row.encoding,
        amount_sign=row.amount_sign.value
        if hasattr(row.amount_sign, "value")
        else str(row.amount_sign),
        is_active=row.is_active,
        notes=row.notes,
        created_by_user_id=row.created_by_user_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _run_to_response(row: BankImportRun) -> BankImportRunResponse:
    return BankImportRunResponse(
        id=row.id,
        account_id=row.account_id,
        mapping_id=row.mapping_id,
        filename=row.filename,
        imported_at=row.imported_at,
        imported_by_user_id=row.imported_by_user_id,
        row_count=row.row_count,
        inserted_count=row.inserted_count,
        duplicate_count=row.duplicate_count,
        error_count=row.error_count,
        notes=row.notes,
    )


def _txn_to_response(row: BankTransaction) -> BankTransactionResponse:
    return BankTransactionResponse(
        id=row.id,
        account_id=row.account_id,
        import_run_id=row.import_run_id,
        imported_at=row.imported_at,
        occurred_on=row.occurred_on,
        description=row.description,
        memo=row.memo,
        amount=row.amount,
        running_balance=row.running_balance,
        fitid=row.fitid,
        external_hash=row.external_hash,
        state=row.state.value if hasattr(row.state, "value") else str(row.state),
        matched_journal_line_id=row.matched_journal_line_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


# --- Mappings --------------------------------------------------------------


@mappings_router.post(
    "", response_model=BankImportMappingResponse, status_code=status.HTTP_201_CREATED
)
async def create_mapping(
    payload: BankImportMappingCreate,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role("owner", "bookkeeper"))],
) -> BankImportMappingResponse:
    try:
        row = await service.create_mapping(
            session,
            name=payload.name,
            account_id=payload.account_id,
            file_kind=payload.file_kind,
            column_map=payload.column_map,
            date_format=payload.date_format,
            delimiter=payload.delimiter,
            has_header=payload.has_header,
            encoding=payload.encoding,
            amount_sign=payload.amount_sign,
            notes=payload.notes,
            actor_user_id=actor.id,
        )
    except Exception as exc:
        await session.rollback()
        raise _map_error(exc) from None
    await session.refresh(row, ["created_at", "updated_at"])
    await session.commit()
    return _mapping_to_response(row)


@mappings_router.get("", response_model=BankImportMappingListResponse)
async def list_mappings(
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(require_role("owner", "bookkeeper", "sales", "viewer"))],
    account_id: Annotated[uuid.UUID | None, Query()] = None,
    include_inactive: Annotated[bool, Query()] = False,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
) -> BankImportMappingListResponse:
    rows = await service.list_mappings(
        session,
        account_id=account_id,
        include_inactive=include_inactive,
        limit=limit,
    )
    return BankImportMappingListResponse(items=[_mapping_to_response(r) for r in rows])


@mappings_router.get("/{mapping_id}", response_model=BankImportMappingResponse)
async def get_mapping(
    mapping_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(require_role("owner", "bookkeeper", "sales", "viewer"))],
) -> BankImportMappingResponse:
    try:
        row = await service.get_mapping(session, mapping_id)
    except Exception as exc:
        raise _map_error(exc) from None
    return _mapping_to_response(row)


@mappings_router.patch("/{mapping_id}", response_model=BankImportMappingResponse)
async def update_mapping(
    mapping_id: uuid.UUID,
    payload: BankImportMappingUpdate,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role("owner", "bookkeeper"))],
) -> BankImportMappingResponse:
    patch = payload.model_dump(exclude_unset=True)
    try:
        row = await service.update_mapping(
            session, mapping_id=mapping_id, patch=patch, actor_user_id=actor.id
        )
    except Exception as exc:
        await session.rollback()
        raise _map_error(exc) from None
    await session.refresh(row, ["created_at", "updated_at"])
    await session.commit()
    return _mapping_to_response(row)


@mappings_router.post("/{mapping_id}/deactivate", response_model=BankImportMappingResponse)
async def deactivate_mapping(
    mapping_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role("owner", "bookkeeper"))],
) -> BankImportMappingResponse:
    try:
        row = await service.deactivate_mapping(
            session, mapping_id=mapping_id, actor_user_id=actor.id
        )
    except Exception as exc:
        await session.rollback()
        raise _map_error(exc) from None
    await session.refresh(row, ["created_at", "updated_at"])
    await session.commit()
    return _mapping_to_response(row)


# --- Imports ---------------------------------------------------------------


@imports_router.post("", response_model=BankImportRunResponse, status_code=status.HTTP_201_CREATED)
async def import_file(
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role("owner", "bookkeeper"))],
    account_id: Annotated[uuid.UUID, Form()],
    file: Annotated[UploadFile, File()],
    mapping_id: Annotated[uuid.UUID | None, Form()] = None,
) -> BankImportRunResponse:
    content = await file.read()
    try:
        run = await service.import_file(
            session,
            account_id=account_id,
            filename=file.filename or "upload.bin",
            file_bytes=content,
            mapping_id=mapping_id,
            actor_user_id=actor.id,
        )
    except Exception as exc:
        await session.rollback()
        raise _map_error(exc) from None
    await session.refresh(run, ["imported_at"])
    await session.commit()
    return _run_to_response(run)


@imports_router.get("/{run_id}", response_model=BankImportRunResponse)
async def get_import_run(
    run_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(require_role("owner", "bookkeeper", "sales", "viewer"))],
) -> BankImportRunResponse:
    try:
        row = await service.get_run(session, run_id)
    except Exception as exc:
        raise _map_error(exc) from None
    return _run_to_response(row)


# --- Transactions ----------------------------------------------------------


@transactions_router.get("", response_model=BankTransactionListResponse)
async def list_transactions(
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(require_role("owner", "bookkeeper", "sales", "viewer"))],
    account_id: Annotated[uuid.UUID | None, Query()] = None,
    state: Annotated[str | None, Query()] = None,
    date_from: Annotated[date | None, Query()] = None,
    date_to: Annotated[date | None, Query()] = None,
    search: Annotated[str | None, Query()] = None,
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> BankTransactionListResponse:
    try:
        rows, next_cursor = await service.list_transactions(
            session,
            account_id=account_id,
            state=state,
            date_from=date_from,
            date_to=date_to,
            search=search,
            limit=limit,
            cursor=cursor,
        )
    except Exception as exc:
        raise _map_error(exc) from None
    return BankTransactionListResponse(
        items=[_txn_to_response(r) for r in rows], next_cursor=next_cursor
    )
