"""Journal-entries endpoints (Phase 4.2, #65).

Thin layer over ``app.services.journal_entries`` + the
``account_balance`` read model. Routers commit the transaction, map
service-layer errors to HTTP, and gate each route on role.

Natural-sign rule
-----------------
``account_balance`` stores only ``total_debits`` / ``total_credits``.
The signed net balance is computed at READ time using the account's
type:

- asset, expense       → ``balance = total_debits - total_credits``
- liability, equity,   → ``balance = total_credits - total_debits``
  revenue
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated, cast

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_role
from app.core.db import get_session
from app.models.account import Account
from app.models.account_balance import AccountBalance
from app.models.approval_request import ApprovalRequest, ApprovalState
from app.models.auth import User
from app.models.journal_entry import JournalEntry
from app.models.journal_line import JournalLine
from app.schemas.accounts import AccountTypeLiteral
from app.schemas.approvals import JournalEntryPendingApprovalResponse
from app.schemas.journal_entries import (
    AccountBalanceListResponse,
    AccountBalanceResponse,
    JournalEntryCreate,
    JournalEntryListResponse,
    JournalEntryResponse,
    JournalEntryReverseRequest,
    JournalLineResponse,
)
from app.services import journal_entries as je_service
from app.services.approvals import (
    ApprovalAlreadyConsumedError,
    ApprovalRequestNotFoundError,
    ApprovalsService,
    ApprovalsServiceError,
)

router = APIRouter(prefix="/accounting", tags=["accounting"])

# Asset/expense are debit-normal; liability/equity/revenue are credit-normal.
_DEBIT_NORMAL: frozenset[str] = frozenset({"asset", "expense"})


def _natural_balance(account_type: str, debits: Decimal, credits: Decimal) -> Decimal:
    if account_type in _DEBIT_NORMAL:
        return debits - credits
    return credits - debits


async def _account_lookup(
    session: AsyncSession, account_ids: set[uuid.UUID]
) -> dict[uuid.UUID, Account]:
    if not account_ids:
        return {}
    rows = (
        (await session.execute(select(Account).where(Account.id.in_(account_ids)))).scalars().all()
    )
    return {row.id: row for row in rows}


def _line_to_response(line: JournalLine, account: Account) -> JournalLineResponse:
    return JournalLineResponse(
        id=line.id,
        account_id=line.account_id,
        account_code=account.code,
        account_name=account.name,
        account_type=cast(AccountTypeLiteral, account.type),
        division_id=line.division_id,
        debit=line.debit,
        credit=line.credit,
        line_number=line.line_number,
        memo=line.memo,
    )


async def _entry_to_response(session: AsyncSession, entry: JournalEntry) -> JournalEntryResponse:
    account_ids = {line.account_id for line in entry.lines}
    accounts = await _account_lookup(session, account_ids)
    return JournalEntryResponse(
        id=entry.id,
        entry_number=entry.entry_number,
        posted_at=entry.posted_at,
        period_id=entry.period_id,
        description=entry.description,
        actor_user_id=entry.actor_user_id,
        is_reversed=entry.is_reversed,
        reversal_of_entry_id=entry.reversal_of_entry_id,
        created_at=entry.created_at,
        lines=[
            _line_to_response(line, accounts[line.account_id])
            for line in sorted(entry.lines, key=lambda ln: ln.line_number)
        ],
    )


def _map_service_error(exc: je_service.JournalEntriesServiceError) -> HTTPException:
    if isinstance(exc, je_service.JournalEntryNotFoundError):
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="journal entry not found"
        )
    if isinstance(exc, je_service.AccountNotFoundError):
        return HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"account not found: {exc}",
        )
    if isinstance(exc, je_service.NoMatchingPeriodError | je_service.PeriodNotOpenError):
        return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


# ---------------------------------------------------------------------------
# Entries
# ---------------------------------------------------------------------------


@router.post(
    "/entries",
    response_model=JournalEntryResponse | JournalEntryPendingApprovalResponse,
    status_code=status.HTTP_201_CREATED,
)
async def post_entry(
    payload: JournalEntryCreate,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role("owner", "bookkeeper"))],
) -> JournalEntryResponse | JournalEntryPendingApprovalResponse:
    lines = [
        je_service.JournalLineInput(
            account_id=ln.account_id,
            division_id=ln.division_id,
            debit=ln.debit,
            credit=ln.credit,
            line_number=ln.line_number,
            memo=ln.memo,
        )
        for ln in payload.lines
    ]
    try:
        result = await je_service.post(
            je_service.JournalEntryInput(
                description=payload.description,
                posted_at=payload.posted_at,
                lines=lines,
            ),
            session=session,
            actor_user_id=actor.id,
        )
    except je_service.JournalEntriesServiceError as exc:
        await session.rollback()
        raise _map_service_error(exc) from None
    if isinstance(result, ApprovalRequest):
        # Above threshold — entry was queued for approval, not posted.
        approval_id = result.id
        await session.commit()
        response.status_code = status.HTTP_202_ACCEPTED
        return JournalEntryPendingApprovalResponse(
            approval_request_id=approval_id,
        )
    entry_response = await _entry_to_response(session, result)
    await session.commit()
    return entry_response


@router.post(
    "/entries/from-approval/{approval_request_id}",
    response_model=JournalEntryResponse,
    status_code=status.HTTP_201_CREATED,
)
async def post_entry_from_approval(
    approval_request_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(require_role("owner", "bookkeeper"))],
) -> JournalEntryResponse:
    """Dispatch a previously approved large-journal-entry approval into a
    posted entry.

    Preserves the original requester as ``actor_user_id`` so audit /
    balance attribution stays accurate. The post call sets
    ``_internal_skip_approval_check=True`` — the request already passed
    the gate when it was approved.
    """
    try:
        approval = await ApprovalsService.get(approval_request_id, session=session)
    except ApprovalRequestNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from None
    if approval.request_type != "accounting.large_journal_entry":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(f"approval request {approval_request_id} is not a " "journal-entry approval"),
        )
    if approval.state != ApprovalState.APPROVED.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"approval request {approval_request_id} is " f"{approval.state}, not approved"
            ),
        )
    if approval.consumed_at is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(f"approval request {approval_request_id} has already " "been consumed"),
        )

    snapshot = approval.payload
    snapshot_lines = [
        je_service.JournalLineInput(
            account_id=uuid.UUID(str(ln["account_id"])),
            division_id=(uuid.UUID(str(ln["division_id"])) if ln.get("division_id") else None),
            debit=ln["debit"],
            credit=ln["credit"],
            line_number=int(ln["line_number"]),
            memo=ln.get("memo"),
        )
        for ln in snapshot["lines"]
    ]
    try:
        entry = await je_service.post(
            je_service.JournalEntryInput(
                description=str(snapshot["description"]),
                posted_at=datetime.fromisoformat(str(snapshot["posted_at"])),
                lines=snapshot_lines,
            ),
            session=session,
            actor_user_id=approval.requested_by_user_id,
            _internal_skip_approval_check=True,
        )
        try:
            await ApprovalsService.mark_consumed(approval_request_id, session=session)
        except ApprovalsServiceError as exc:
            await session.rollback()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(exc),
            ) from None
    except je_service.JournalEntriesServiceError as exc:
        await session.rollback()
        raise _map_service_error(exc) from None
    except ApprovalAlreadyConsumedError as exc:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from None

    assert isinstance(entry, JournalEntry)
    entry_response = await _entry_to_response(session, entry)
    await session.commit()
    return entry_response


@router.post(
    "/entries/{entry_id}/reverse",
    response_model=JournalEntryResponse,
    status_code=status.HTTP_201_CREATED,
)
async def reverse_entry(
    entry_id: uuid.UUID,
    payload: JournalEntryReverseRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role("owner", "bookkeeper"))],
) -> JournalEntryResponse:
    try:
        reversal = await je_service.reverse(
            entry_id,
            session=session,
            actor_user_id=actor.id,
            description=payload.description,
        )
    except je_service.JournalEntriesServiceError as exc:
        await session.rollback()
        raise _map_service_error(exc) from None
    response = await _entry_to_response(session, reversal)
    await session.commit()
    return response


@router.get("/entries", response_model=JournalEntryListResponse)
async def list_entries(
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(require_role("owner", "bookkeeper"))],
    account_id: Annotated[uuid.UUID | None, Query()] = None,
    posted_at_from: Annotated[datetime | None, Query()] = None,
    posted_at_to: Annotated[datetime | None, Query()] = None,
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> JournalEntryListResponse:
    try:
        page = await je_service.list_entries(
            session=session,
            account_id=account_id,
            posted_at_from=posted_at_from,
            posted_at_to=posted_at_to,
            cursor=cursor,
            limit=limit,
        )
    except je_service.JournalEntriesServiceError as exc:
        raise _map_service_error(exc) from None
    items = [await _entry_to_response(session, e) for e in page.items]
    return JournalEntryListResponse(items=items, next_cursor=page.next_cursor)


@router.get("/entries/{entry_id}", response_model=JournalEntryResponse)
async def get_entry(
    entry_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(require_role("owner", "bookkeeper"))],
) -> JournalEntryResponse:
    try:
        entry = await je_service.get(entry_id, session=session)
    except je_service.JournalEntriesServiceError as exc:
        raise _map_service_error(exc) from None
    return await _entry_to_response(session, entry)


# ---------------------------------------------------------------------------
# Account balances
# ---------------------------------------------------------------------------


def _balance_response(account: Account, row: AccountBalance | None) -> AccountBalanceResponse:
    debits = row.total_debits if row is not None else Decimal("0")
    credits = row.total_credits if row is not None else Decimal("0")
    updated_at = row.updated_at if row is not None else account.updated_at
    return AccountBalanceResponse(
        account_id=account.id,
        account_code=account.code,
        account_name=account.name,
        account_type=cast(AccountTypeLiteral, account.type),
        total_debits=debits,
        total_credits=credits,
        balance=_natural_balance(account.type, debits, credits),
        updated_at=updated_at,
    )


@router.get("/account-balances", response_model=AccountBalanceListResponse)
async def list_account_balances(
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(require_role("owner", "bookkeeper"))],
    account_id: Annotated[uuid.UUID | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
) -> AccountBalanceListResponse:
    """Return per-account balances.

    A row with no posted activity yet still appears here with zero
    totals (we left-join Account → AccountBalance). Single-account
    lookup via ``?account_id=`` always returns one row, even if no
    activity has accumulated.
    """
    stmt = select(Account).where(Account.is_archived.is_(False))
    if account_id is not None:
        stmt = select(Account).where(Account.id == account_id)
    stmt = stmt.order_by(Account.code).limit(limit)
    accounts = list((await session.execute(stmt)).scalars().all())

    if not accounts:
        return AccountBalanceListResponse(items=[], next_cursor=None)

    balance_rows = (
        (
            await session.execute(
                select(AccountBalance).where(
                    AccountBalance.account_id.in_([a.id for a in accounts])
                )
            )
        )
        .scalars()
        .all()
    )
    by_id = {row.account_id: row for row in balance_rows}

    return AccountBalanceListResponse(
        items=[_balance_response(a, by_id.get(a.id)) for a in accounts],
        next_cursor=None,
    )
