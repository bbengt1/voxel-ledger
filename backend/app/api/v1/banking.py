"""Banking endpoints (Phase 8.9, #136).

Thin layer over ``app.services.bank_imports``. Owner + bookkeeper write
(mappings + import); owner + bookkeeper + sales + viewer read.

The ``POST /api/v1/bank-imports`` endpoint accepts a multipart upload
(``file`` + ``account_id`` + optional ``mapping_id``). OFX uploads can
skip the mapping; CSV uploads must reference one.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
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
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_role
from app.core.db import get_session
from app.events.types import banking as banking_events
from app.models.auth import User
from app.models.bank import BankImportMapping, BankImportRun, BankTransaction, BankTransactionState
from app.models.bank_match_rule import BankMatchRule
from app.models.bank_reconciliation import (
    BankReconciliation,
    BankReconciliationItem,
)
from app.models.journal_entry import JournalEntry
from app.models.journal_line import JournalLine
from app.schemas.banking import (
    BankAutoMatchResultItem,
    BankAutoMatchRunResponse,
    BankImportMappingCreate,
    BankImportMappingListResponse,
    BankImportMappingResponse,
    BankImportMappingUpdate,
    BankImportRunResponse,
    BankMatchRuleCreate,
    BankMatchRuleListResponse,
    BankMatchRuleResponse,
    BankMatchRuleUpdate,
    BankPostJournalEntryRequest,
    BankReconciliationCreate,
    BankReconciliationItemResponse,
    BankReconciliationListResponse,
    BankReconciliationResponse,
    BankTransactionListResponse,
    BankTransactionMatchRequest,
    BankTransactionResponse,
    InterAccountTransferRequest,
    InterAccountTransferResponse,
)
from app.schemas.events import EventCreate
from app.services import bank_auto_matcher as auto_matcher_service
from app.services import bank_imports as service
from app.services import bank_match_rules as rules_service
from app.services import bank_reconciliation as recon_service
from app.services import event_store
from app.services import inter_account_transfers as transfers_service
from app.services import journal_entries as journal_service

mappings_router = APIRouter(prefix="/bank-import-mappings", tags=["banking"])
imports_router = APIRouter(prefix="/bank-imports", tags=["banking"])
transactions_router = APIRouter(prefix="/bank-transactions", tags=["banking"])
match_rules_router = APIRouter(prefix="/bank-match-rules", tags=["banking"])
reconciliations_router = APIRouter(prefix="/bank-reconciliations", tags=["banking"])
transfers_router = APIRouter(prefix="/inter-account-transfers", tags=["banking"])


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
    if isinstance(exc, rules_service.BankMatchRuleNotFoundError):
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="bank match rule not found"
        )
    if isinstance(exc, rules_service.InvalidBankMatchRuleError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, rules_service.BankMatchRulesServiceError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, recon_service.BankReconciliationNotFoundError):
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="bank reconciliation not found"
        )
    if isinstance(exc, recon_service.BankReconciliationItemNotFoundError):
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="bank reconciliation item not found",
        )
    if isinstance(exc, recon_service.BankReconciliationFinalizedError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, recon_service.InvalidBankReconciliationError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, recon_service.BankReconciliationServiceError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, transfers_service.InvalidInterAccountTransferError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, transfers_service.InterAccountTransfersServiceError):
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


# --- Match rules (Phase 8.10, #137) ----------------------------------------


def _rule_to_response(row: BankMatchRule) -> BankMatchRuleResponse:
    return BankMatchRuleResponse(
        id=row.id,
        account_id=row.account_id,
        priority=row.priority,
        match_kind=(
            row.match_kind.value if hasattr(row.match_kind, "value") else str(row.match_kind)
        ),
        match_field=(
            row.match_field.value if hasattr(row.match_field, "value") else str(row.match_field)
        ),
        match_value=row.match_value,
        action_kind=(
            row.action_kind.value if hasattr(row.action_kind, "value") else str(row.action_kind)
        ),
        debit_account_id=row.debit_account_id,
        credit_account_id=row.credit_account_id,
        min_amount=row.min_amount,
        max_amount=row.max_amount,
        description_template=row.description_template,
        is_active=row.is_active,
        notes=row.notes,
        created_by_user_id=row.created_by_user_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@match_rules_router.post(
    "", response_model=BankMatchRuleResponse, status_code=status.HTTP_201_CREATED
)
async def create_match_rule(
    payload: BankMatchRuleCreate,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role("owner", "bookkeeper"))],
) -> BankMatchRuleResponse:
    try:
        row = await rules_service.create(
            session=session,
            account_id=payload.account_id,
            priority=payload.priority,
            match_kind=payload.match_kind,
            match_field=payload.match_field,
            match_value=payload.match_value,
            action_kind=payload.action_kind,
            debit_account_id=payload.debit_account_id,
            credit_account_id=payload.credit_account_id,
            min_amount=payload.min_amount,
            max_amount=payload.max_amount,
            description_template=payload.description_template,
            notes=payload.notes,
            actor_user_id=actor.id,
        )
    except Exception as exc:
        await session.rollback()
        raise _map_error(exc) from None
    await session.refresh(row, ["created_at", "updated_at"])
    await session.commit()
    return _rule_to_response(row)


@match_rules_router.get("", response_model=BankMatchRuleListResponse)
async def list_match_rules(
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(require_role("owner", "bookkeeper", "sales", "viewer"))],
    account_id: Annotated[uuid.UUID | None, Query()] = None,
    include_inactive: Annotated[bool, Query()] = False,
    only_account_id: Annotated[bool, Query()] = False,
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
) -> BankMatchRuleListResponse:
    rows = await rules_service.list_rules(
        session=session,
        account_id=account_id,
        include_inactive=include_inactive,
        only_account_id=only_account_id,
        limit=limit,
    )
    return BankMatchRuleListResponse(items=[_rule_to_response(r) for r in rows])


@match_rules_router.get("/{rule_id}", response_model=BankMatchRuleResponse)
async def get_match_rule(
    rule_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(require_role("owner", "bookkeeper", "sales", "viewer"))],
) -> BankMatchRuleResponse:
    try:
        row = await rules_service.get(session, rule_id)
    except Exception as exc:
        raise _map_error(exc) from None
    return _rule_to_response(row)


@match_rules_router.patch("/{rule_id}", response_model=BankMatchRuleResponse)
async def update_match_rule(
    rule_id: uuid.UUID,
    payload: BankMatchRuleUpdate,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role("owner", "bookkeeper"))],
) -> BankMatchRuleResponse:
    patch = payload.model_dump(exclude_unset=True)
    try:
        row = await rules_service.update(
            session=session, rule_id=rule_id, patch=patch, actor_user_id=actor.id
        )
    except Exception as exc:
        await session.rollback()
        raise _map_error(exc) from None
    await session.refresh(row, ["created_at", "updated_at"])
    await session.commit()
    return _rule_to_response(row)


@match_rules_router.post("/{rule_id}/deactivate", response_model=BankMatchRuleResponse)
async def deactivate_match_rule(
    rule_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role("owner", "bookkeeper"))],
) -> BankMatchRuleResponse:
    try:
        row = await rules_service.deactivate(
            session=session, rule_id=rule_id, actor_user_id=actor.id
        )
    except Exception as exc:
        await session.rollback()
        raise _map_error(exc) from None
    await session.refresh(row, ["created_at", "updated_at"])
    await session.commit()
    return _rule_to_response(row)


@match_rules_router.post("/run-now", response_model=BankAutoMatchRunResponse)
async def run_match_rules_now(
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role("owner", "bookkeeper"))],
) -> BankAutoMatchRunResponse:
    try:
        results = await auto_matcher_service.run_once(session=session, actor_user_id=actor.id)
    except Exception as exc:
        await session.rollback()
        raise _map_error(exc) from None
    await session.commit()
    return BankAutoMatchRunResponse(
        count=len(results),
        items=[
            BankAutoMatchResultItem(
                transaction_id=r.transaction_id,
                rule_id=r.rule_id,
                action_kind=r.action_kind,
                journal_entry_id=r.journal_entry_id,
            )
            for r in results
        ],
    )


# --- Bank transaction manual match endpoints (Phase 8.10, #137) ------------


async def _load_transaction(session: AsyncSession, tx_id: uuid.UUID) -> BankTransaction:
    row = (
        await session.execute(select(BankTransaction).where(BankTransaction.id == tx_id))
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="bank transaction not found")
    return row


async def _emit_tx_event(
    session: AsyncSession,
    *,
    event_type: str,
    tx_id: uuid.UUID,
    payload: dict,
    actor_user_id: uuid.UUID | None,
) -> None:
    await event_store.append(
        EventCreate(
            type=event_type,
            aggregate_type=banking_events.AGGREGATE_TYPE_BANK_TRANSACTION,
            aggregate_id=tx_id,
            payload=payload,
            occurred_at=datetime.now(UTC),
            correlation_id=uuid.uuid4(),
            actor_user_id=actor_user_id,
        ),
        session=session,
    )


@transactions_router.post("/{tx_id}/match", response_model=BankTransactionResponse)
async def match_transaction(
    tx_id: uuid.UUID,
    payload: BankTransactionMatchRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role("owner", "bookkeeper"))],
) -> BankTransactionResponse:
    tx = await _load_transaction(session, tx_id)
    entry = (
        await session.execute(
            select(JournalEntry).where(JournalEntry.id == payload.journal_entry_id)
        )
    ).scalar_one_or_none()
    if entry is None:
        raise HTTPException(status_code=404, detail="journal entry not found")
    line = (
        await session.execute(
            select(JournalLine).where(
                JournalLine.entry_id == entry.id,
                JournalLine.account_id == tx.account_id,
            )
        )
    ).scalar_one_or_none()
    if line is None:
        raise HTTPException(
            status_code=400,
            detail="journal entry has no line referencing the bank account",
        )
    tx.matched_journal_line_id = line.id
    tx.state = BankTransactionState.MATCHED
    await session.flush()
    await _emit_tx_event(
        session,
        event_type=banking_events.TYPE_BANK_TRANSACTION_MANUALLY_MATCHED,
        tx_id=tx.id,
        payload={
            "transaction_id": str(tx.id),
            "journal_entry_id": str(entry.id),
            "journal_line_id": str(line.id),
        },
        actor_user_id=actor.id,
    )
    await session.refresh(tx, ["created_at", "updated_at"])
    await session.commit()
    return _txn_to_response(tx)


@transactions_router.post("/{tx_id}/unmatch", response_model=BankTransactionResponse)
async def unmatch_transaction(
    tx_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role("owner", "bookkeeper"))],
) -> BankTransactionResponse:
    tx = await _load_transaction(session, tx_id)
    previous = tx.matched_journal_line_id
    tx.matched_journal_line_id = None
    tx.state = BankTransactionState.UNMATCHED
    await session.flush()
    await _emit_tx_event(
        session,
        event_type=banking_events.TYPE_BANK_TRANSACTION_UNMATCHED,
        tx_id=tx.id,
        payload={
            "transaction_id": str(tx.id),
            "previous_journal_line_id": str(previous) if previous else None,
        },
        actor_user_id=actor.id,
    )
    await session.refresh(tx, ["created_at", "updated_at"])
    await session.commit()
    return _txn_to_response(tx)


@transactions_router.post("/{tx_id}/ignore", response_model=BankTransactionResponse)
async def ignore_transaction(
    tx_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role("owner", "bookkeeper"))],
) -> BankTransactionResponse:
    tx = await _load_transaction(session, tx_id)
    tx.state = BankTransactionState.IGNORED
    await session.flush()
    await _emit_tx_event(
        session,
        event_type=banking_events.TYPE_BANK_TRANSACTION_IGNORED,
        tx_id=tx.id,
        payload={"transaction_id": str(tx.id), "rule_id": None},
        actor_user_id=actor.id,
    )
    await session.refresh(tx, ["created_at", "updated_at"])
    await session.commit()
    return _txn_to_response(tx)


@transactions_router.post("/{tx_id}/post-journal-entry", response_model=BankTransactionResponse)
async def post_je_and_match_transaction(
    tx_id: uuid.UUID,
    payload: BankPostJournalEntryRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role("owner", "bookkeeper"))],
) -> BankTransactionResponse:
    tx = await _load_transaction(session, tx_id)
    if not any(line.account_id == tx.account_id for line in payload.lines):
        raise HTTPException(
            status_code=400,
            detail="at least one line must reference the bank account",
        )
    lines_in = [
        journal_service.JournalLineInput(
            account_id=line.account_id,
            debit=Decimal(line.debit),
            credit=Decimal(line.credit),
            line_number=line.line_number,
            memo=line.memo,
        )
        for line in payload.lines
    ]
    try:
        entry = await journal_service.post(
            journal_service.JournalEntryInput(
                description=payload.description,
                posted_at=payload.posted_at,
                lines=lines_in,
            ),
            session=session,
            actor_user_id=actor.id,
            _internal_skip_approval_check=True,
        )
    except journal_service.JournalEntriesServiceError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from None
    if not isinstance(entry, JournalEntry):
        # Approval-gated branch — shouldn't be reachable with the skip flag.
        await session.rollback()
        raise HTTPException(status_code=400, detail="journal entry not posted")

    line = (
        await session.execute(
            select(JournalLine).where(
                JournalLine.entry_id == entry.id,
                JournalLine.account_id == tx.account_id,
            )
        )
    ).scalar_one_or_none()
    if line is None:
        await session.rollback()
        raise HTTPException(
            status_code=400,
            detail="journal entry has no line referencing the bank account",
        )
    tx.matched_journal_line_id = line.id
    tx.state = BankTransactionState.MATCHED
    await session.flush()
    await _emit_tx_event(
        session,
        event_type=banking_events.TYPE_BANK_TRANSACTION_MANUALLY_MATCHED,
        tx_id=tx.id,
        payload={
            "transaction_id": str(tx.id),
            "journal_entry_id": str(entry.id),
            "journal_line_id": str(line.id),
        },
        actor_user_id=actor.id,
    )
    await session.refresh(tx, ["created_at", "updated_at"])
    await session.commit()
    return _txn_to_response(tx)


# --- Bank reconciliation (Phase 8.11, #138) --------------------------------


def _item_to_response(row: BankReconciliationItem) -> BankReconciliationItemResponse:
    return BankReconciliationItemResponse(
        id=row.id,
        reconciliation_id=row.reconciliation_id,
        bank_transaction_id=row.bank_transaction_id,
        is_cleared=row.is_cleared,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _recon_to_response(
    row: BankReconciliation,
    items: list[BankReconciliationItem] | None = None,
) -> BankReconciliationResponse:
    return BankReconciliationResponse(
        id=row.id,
        account_id=row.account_id,
        period_start=row.period_start,
        period_end=row.period_end,
        statement_ending_balance=row.statement_ending_balance,
        book_ending_balance=row.book_ending_balance,
        difference=row.difference,
        state=row.state.value if hasattr(row.state, "value") else str(row.state),
        finalized_at=row.finalized_at,
        finalized_by_user_id=row.finalized_by_user_id,
        notes=row.notes,
        created_by_user_id=row.created_by_user_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
        items=[_item_to_response(i) for i in (items or [])],
    )


@reconciliations_router.post(
    "", response_model=BankReconciliationResponse, status_code=status.HTTP_201_CREATED
)
async def create_reconciliation(
    payload: BankReconciliationCreate,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role("owner", "bookkeeper"))],
) -> BankReconciliationResponse:
    try:
        row = await recon_service.create(
            session=session,
            account_id=payload.account_id,
            period_start=payload.period_start,
            period_end=payload.period_end,
            statement_ending_balance=payload.statement_ending_balance,
            notes=payload.notes,
            actor_user_id=actor.id,
        )
    except Exception as exc:
        await session.rollback()
        raise _map_error(exc) from None
    items = await recon_service.list_items(session, row.id)
    await session.refresh(row, ["created_at", "updated_at"])
    await session.commit()
    return _recon_to_response(row, items)


@reconciliations_router.get("", response_model=BankReconciliationListResponse)
async def list_reconciliations(
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(require_role("owner", "bookkeeper", "sales", "viewer"))],
    account_id: Annotated[uuid.UUID | None, Query()] = None,
    state: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> BankReconciliationListResponse:
    try:
        rows = await recon_service.list_reconciliations(
            session=session, account_id=account_id, state=state, limit=limit
        )
    except Exception as exc:
        raise _map_error(exc) from None
    return BankReconciliationListResponse(items=[_recon_to_response(r) for r in rows])


@reconciliations_router.get("/{recon_id}", response_model=BankReconciliationResponse)
async def get_reconciliation(
    recon_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(require_role("owner", "bookkeeper", "sales", "viewer"))],
) -> BankReconciliationResponse:
    try:
        row = await recon_service.get(session, recon_id)
        items = await recon_service.list_items(session, row.id)
    except Exception as exc:
        raise _map_error(exc) from None
    return _recon_to_response(row, items)


@reconciliations_router.post(
    "/{recon_id}/items/{item_id}/clear", response_model=BankReconciliationItemResponse
)
async def clear_item(
    recon_id: uuid.UUID,
    item_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role("owner", "bookkeeper"))],
) -> BankReconciliationItemResponse:
    try:
        item = await recon_service.toggle_cleared(
            session=session, item_id=item_id, is_cleared=True, actor_user_id=actor.id
        )
        if item.reconciliation_id != recon_id:
            raise HTTPException(status_code=404, detail="bank reconciliation item not found")
    except HTTPException:
        await session.rollback()
        raise
    except Exception as exc:
        await session.rollback()
        raise _map_error(exc) from None
    await session.refresh(item, ["created_at", "updated_at"])
    await session.commit()
    return _item_to_response(item)


@reconciliations_router.post(
    "/{recon_id}/items/{item_id}/unclear", response_model=BankReconciliationItemResponse
)
async def unclear_item(
    recon_id: uuid.UUID,
    item_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role("owner", "bookkeeper"))],
) -> BankReconciliationItemResponse:
    try:
        item = await recon_service.toggle_cleared(
            session=session, item_id=item_id, is_cleared=False, actor_user_id=actor.id
        )
        if item.reconciliation_id != recon_id:
            raise HTTPException(status_code=404, detail="bank reconciliation item not found")
    except HTTPException:
        await session.rollback()
        raise
    except Exception as exc:
        await session.rollback()
        raise _map_error(exc) from None
    await session.refresh(item, ["created_at", "updated_at"])
    await session.commit()
    return _item_to_response(item)


@reconciliations_router.post("/{recon_id}/recompute", response_model=BankReconciliationResponse)
async def recompute_reconciliation(
    recon_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role("owner", "bookkeeper"))],
) -> BankReconciliationResponse:
    _ = actor
    try:
        row = await recon_service.recompute_balance(session=session, reconciliation_id=recon_id)
        items = await recon_service.list_items(session, row.id)
    except Exception as exc:
        await session.rollback()
        raise _map_error(exc) from None
    await session.refresh(row, ["created_at", "updated_at"])
    await session.commit()
    return _recon_to_response(row, items)


@reconciliations_router.post("/{recon_id}/finalize", response_model=BankReconciliationResponse)
async def finalize_reconciliation(
    recon_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role("owner", "bookkeeper"))],
) -> BankReconciliationResponse:
    try:
        row = await recon_service.finalize(
            session=session, reconciliation_id=recon_id, actor_user_id=actor.id
        )
        items = await recon_service.list_items(session, row.id)
    except Exception as exc:
        await session.rollback()
        raise _map_error(exc) from None
    await session.refresh(row, ["created_at", "updated_at"])
    await session.commit()
    return _recon_to_response(row, items)


# --- Inter-account transfers (Phase 8.11, #138) ----------------------------


@transfers_router.post(
    "", response_model=InterAccountTransferResponse, status_code=status.HTTP_201_CREATED
)
async def post_inter_account_transfer(
    payload: InterAccountTransferRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role("owner", "bookkeeper"))],
) -> InterAccountTransferResponse:
    try:
        entry = await transfers_service.post_transfer(
            session=session,
            from_account_id=payload.from_account_id,
            to_account_id=payload.to_account_id,
            amount=Decimal(payload.amount),
            occurred_at=payload.occurred_at,
            memo=payload.memo,
            actor_user_id=actor.id,
        )
    except Exception as exc:
        await session.rollback()
        raise _map_error(exc) from None
    await session.commit()
    return InterAccountTransferResponse(journal_entry_id=entry.id)
