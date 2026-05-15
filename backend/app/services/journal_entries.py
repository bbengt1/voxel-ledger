"""Journal-entries service (Phase 4.2, #65).

The double-entry write path. Every accounting mutation downstream
routes through ``post(...)``. Entries are append-only; the only
permitted mutation is flipping ``is_reversed`` from false to true on
the original entry when ``reverse(...)`` posts the cancelling entry.

Invariants enforced here (in addition to the DB CHECK on each line):

* Description is non-empty after strip.
* Two or more lines.
* Each line is debit XOR credit (exactly one > 0, the other == 0).
* Sum of debits equals sum of credits (quantized to 6 places).
* Every line's account exists and is not archived.
* Cannot reverse an already-reversed entry.
* Cannot reverse a reversal entry.

Entry numbers are allocated through ``ReferenceNumberService`` with the
``JE`` prefix. The allocator's atomic upsert serializes concurrent
writers, so two posts can never collide on ``entry_number``.

Reversal flow
-------------
``reverse(original_id, ...)`` builds a new entry with debit and credit
swapped on each line and ``reversal_of_entry_id = original.id``, then
posts it through the normal ``post(...)`` flow (which fires its own
``accounting.JournalEntryPosted`` event and runs the balance
projection). Finally we flip ``is_reversed = true`` on the original
via a raw UPDATE — the PG trigger explicitly allows that one mutation.
An informational ``accounting.JournalEntryReversed`` event is emitted
so the audit log records the link; the balance projection treats this
event as a no-op (the swapped amounts were already applied by the
reversal entry's Posted event).
"""

from __future__ import annotations

import base64
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import and_, desc, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.events.types import accounting as accounting_events
from app.models.account import Account
from app.models.accounting_period import AccountingPeriodState
from app.models.approval_request import ApprovalRequest
from app.models.journal_entry import JournalEntry
from app.models.journal_line import JournalLine
from app.schemas.events import EventCreate
from app.services import accounting_periods as periods_service
from app.services import event_store
from app.services.approvals import ApprovalsService
from app.services.reference_number import ReferenceNumberService
from app.services.settings import SettingsService

# Match Numeric(18, 6).
_QUANTUM = Decimal("0.000001")


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class JournalEntriesServiceError(Exception):
    """Base. Routers default to 400."""


class JournalEntryNotFoundError(JournalEntriesServiceError):
    pass


class JournalEntryEmptyDescriptionError(JournalEntriesServiceError):
    pass


class JournalEntryTooFewLinesError(JournalEntriesServiceError):
    pass


class JournalLineInvalidError(JournalEntriesServiceError):
    """A line violates the debit-XOR-credit invariant."""


class JournalEntryUnbalancedError(JournalEntriesServiceError):
    """sum(debit) != sum(credit)."""


class AccountNotFoundError(JournalEntriesServiceError):
    """An account on a line doesn't exist."""


class AccountArchivedError(JournalEntriesServiceError):
    """An account on a line is archived."""


class JournalEntryAlreadyReversedError(JournalEntriesServiceError):
    pass


class JournalEntryIsReversalError(JournalEntriesServiceError):
    """Tried to reverse an entry that is itself a reversal."""


class InvalidCursorError(JournalEntriesServiceError):
    pass


class NoMatchingPeriodError(JournalEntriesServiceError):
    """posted_at falls outside any defined accounting period."""


class PeriodNotOpenError(JournalEntriesServiceError):
    """The accounting period covering posted_at is closed or locked."""


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------


@dataclass
class JournalLineInput:
    account_id: uuid.UUID
    debit: Decimal
    credit: Decimal
    line_number: int
    memo: str | None = None
    # Optional second analytical dimension introduced in Phase 4.5 (#68).
    # Passes through to the row + event payload; no validation against
    # division archival here — callers above the service layer (or the
    # endpoint schema) should pre-validate. We trust ON DELETE RESTRICT
    # for FK integrity.
    division_id: uuid.UUID | None = None


@dataclass
class JournalEntryInput:
    description: str
    posted_at: datetime
    lines: list[JournalLineInput]


# ---------------------------------------------------------------------------
# Pagination cursor
# ---------------------------------------------------------------------------


def _encode_cursor(posted_at: datetime, entry_number: str) -> str:
    raw = json.dumps({"p": posted_at.isoformat(), "n": entry_number}).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii")


def _decode_cursor(cursor: str) -> tuple[datetime, str]:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("ascii"))
        decoded = json.loads(raw.decode("utf-8"))
        return datetime.fromisoformat(decoded["p"]), str(decoded["n"])
    except (ValueError, KeyError, TypeError) as exc:
        raise InvalidCursorError(f"invalid cursor: {exc}") from exc


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------


def _to_decimal(value: object) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _validate_lines(lines: list[JournalLineInput]) -> None:
    if len(lines) < 2:
        raise JournalEntryTooFewLinesError("a journal entry must have at least 2 lines")
    for line in lines:
        debit = _to_decimal(line.debit)
        credit = _to_decimal(line.credit)
        if debit < 0 or credit < 0:
            raise JournalLineInvalidError(
                f"line {line.line_number}: debit and credit must be non-negative"
            )
        debit_positive = debit > 0
        credit_positive = credit > 0
        if debit_positive == credit_positive:
            # Both positive, or both zero — equally invalid.
            raise JournalLineInvalidError(
                f"line {line.line_number}: exactly one of debit/credit must be > 0 "
                f"(got debit={debit}, credit={credit})"
            )


def _validate_balanced(lines: list[JournalLineInput]) -> None:
    total_debit = sum((_to_decimal(line.debit) for line in lines), Decimal("0")).quantize(_QUANTUM)
    total_credit = sum((_to_decimal(line.credit) for line in lines), Decimal("0")).quantize(
        _QUANTUM
    )
    if total_debit != total_credit:
        delta = total_debit - total_credit
        raise JournalEntryUnbalancedError(
            f"entry is unbalanced: debits={total_debit}, credits={total_credit}, " f"delta={delta}"
        )


async def _load_and_check_accounts(
    session: AsyncSession, lines: list[JournalLineInput]
) -> dict[uuid.UUID, Account]:
    account_ids = {line.account_id for line in lines}
    rows = (
        (await session.execute(select(Account).where(Account.id.in_(account_ids)))).scalars().all()
    )
    by_id = {row.id: row for row in rows}
    for line in lines:
        acct = by_id.get(line.account_id)
        if acct is None:
            raise AccountNotFoundError(str(line.account_id))
        if acct.is_archived:
            raise AccountArchivedError(f"account {acct.code!r} is archived; cannot post to it")
    return by_id


# ---------------------------------------------------------------------------
# post / reverse / list / get
# ---------------------------------------------------------------------------


async def _emit(
    session: AsyncSession,
    *,
    event_type: str,
    aggregate_id: uuid.UUID,
    payload: dict[str, Any],
    actor_user_id: uuid.UUID | None,
) -> None:
    await event_store.append(
        EventCreate(
            type=event_type,
            aggregate_type=accounting_events.AGGREGATE_TYPE_JOURNAL_ENTRY,
            aggregate_id=aggregate_id,
            payload=payload,
            occurred_at=datetime.now(UTC),
            correlation_id=uuid.uuid4(),
            actor_user_id=actor_user_id,
        ),
        session=session,
    )


async def _load_full(session: AsyncSession, entry_id: uuid.UUID) -> JournalEntry:
    """Load an entry + its lines, bypassing the identity-map cache.

    ``populate_existing()`` re-reads from the DB and refreshes any
    instance already in the session — important after the raw UPDATE
    inside :func:`reverse` flips ``is_reversed`` on the original.
    """
    stmt = (
        select(JournalEntry)
        .where(JournalEntry.id == entry_id)
        .options(selectinload(JournalEntry.lines))
        .execution_options(populate_existing=True)
    )
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise JournalEntryNotFoundError(str(entry_id))
    return row


async def post(
    entry_input: JournalEntryInput,
    *,
    session: AsyncSession,
    actor_user_id: uuid.UUID,
    reversal_of_entry_id: uuid.UUID | None = None,
    _internal_skip_approval_check: bool = False,
) -> JournalEntry | ApprovalRequest:
    """Post a balanced journal entry. Returns the persisted header + lines.

    ``reversal_of_entry_id`` is set internally by :func:`reverse`; callers
    should leave it as ``None``.

    Above the configured approval threshold the entry is NOT posted —
    instead a pending :class:`ApprovalRequest` is returned and the caller
    surfaces HTTP 202. The reversal path and the
    ``/from-approval/{id}`` dispatcher pass
    ``_internal_skip_approval_check=True`` to bypass this gate.
    """
    description = (entry_input.description or "").strip()
    if not description:
        raise JournalEntryEmptyDescriptionError("description must not be empty")

    lines = list(entry_input.lines)
    _validate_lines(lines)
    _validate_balanced(lines)
    await _load_and_check_accounts(session, lines)

    # --- Period gating (Phase 4.3) ---
    # Resolve the period covering the entry's business date BEFORE
    # allocating the entry number so a rejected post doesn't consume a
    # JE sequence value.
    posted_date = entry_input.posted_at.date()
    period = await periods_service.find_period_for(posted_date, session=session)
    if period is None:
        raise NoMatchingPeriodError(
            f"posted_at {posted_date.isoformat()} falls outside any defined " f"accounting period"
        )
    if period.state != AccountingPeriodState.OPEN.value:
        raise PeriodNotOpenError(
            f"cannot post to period {period.name!r}: state is " f"{period.state!r} (must be 'open')"
        )

    # --- Threshold gating → approval queue (Phase 4.4) ---
    if not _internal_skip_approval_check and reversal_of_entry_id is None:
        total_debits = sum((_to_decimal(line.debit) for line in lines), Decimal("0")).quantize(
            _QUANTUM
        )
        threshold = await SettingsService.get(
            "accounting.journal_entry.approval_threshold", session=session
        )
        if total_debits > threshold:
            snapshot = {
                "description": description,
                "posted_at": entry_input.posted_at.isoformat(),
                "lines": [
                    {
                        "account_id": str(line.account_id),
                        "debit": _to_decimal(line.debit).quantize(_QUANTUM).to_eng_string(),
                        "credit": _to_decimal(line.credit).quantize(_QUANTUM).to_eng_string(),
                        "line_number": line.line_number,
                        "memo": line.memo,
                        "division_id": (str(line.division_id) if line.division_id else None),
                    }
                    for line in lines
                ],
            }
            return await ApprovalsService.create(
                request_type="accounting.large_journal_entry",
                subject_kind="journal_entry",
                subject_id=uuid.uuid4(),
                payload=snapshot,
                threshold_amount=threshold,
                session=session,
                actor_user_id=actor_user_id,
            )

    entry_number = await ReferenceNumberService.allocate("JE", session=session)

    entry_id = uuid.uuid4()
    entry = JournalEntry(
        id=entry_id,
        entry_number=entry_number,
        posted_at=entry_input.posted_at,
        period_id=period.id,
        description=description,
        actor_user_id=actor_user_id,
        is_reversed=False,
        reversal_of_entry_id=reversal_of_entry_id,
    )
    session.add(entry)

    persisted_lines: list[JournalLine] = []
    for line in lines:
        debit = _to_decimal(line.debit).quantize(_QUANTUM)
        credit = _to_decimal(line.credit).quantize(_QUANTUM)
        row = JournalLine(
            id=uuid.uuid4(),
            entry_id=entry_id,
            account_id=line.account_id,
            division_id=line.division_id,
            debit=debit,
            credit=credit,
            line_number=line.line_number,
            memo=line.memo,
        )
        session.add(row)
        persisted_lines.append(row)

    await session.flush()

    payload: dict[str, Any] = {
        "entry_id": str(entry_id),
        "entry_number": entry_number,
        "posted_at": entry_input.posted_at.isoformat(),
        "period_id": str(period.id),
        "description": description,
        "source_event_id": None,
        "actor_user_id": str(actor_user_id),
        "reversal_of_entry_id": (
            str(reversal_of_entry_id) if reversal_of_entry_id is not None else None
        ),
        "lines": [
            {
                "account_id": str(line.account_id),
                "debit": _to_decimal(line.debit).quantize(_QUANTUM).to_eng_string(),
                "credit": _to_decimal(line.credit).quantize(_QUANTUM).to_eng_string(),
                "line_number": line.line_number,
                "memo": line.memo,
                "division_id": str(line.division_id) if line.division_id else None,
            }
            for line in lines
        ],
    }

    await _emit(
        session,
        event_type=accounting_events.TYPE_JOURNAL_ENTRY_POSTED,
        aggregate_id=entry_id,
        payload=payload,
        actor_user_id=actor_user_id,
    )

    return await _load_full(session, entry_id)


async def reverse(
    entry_id: uuid.UUID,
    *,
    session: AsyncSession,
    actor_user_id: uuid.UUID,
    description: str | None = None,
) -> JournalEntry:
    """Post a cancelling reversal entry and flag the original as reversed.

    The reversal swaps each line's debit ↔ credit. Posting the new entry
    runs through the normal ``post(...)`` validation path, so the
    balance projection has already applied the cancelling deltas by the
    time we return. The trailing ``JournalEntryReversed`` event is
    informational (audit) — it does not move balances.
    """
    original = await _load_full(session, entry_id)
    if original.is_reversed:
        raise JournalEntryAlreadyReversedError(f"entry {original.entry_number} is already reversed")
    if original.reversal_of_entry_id is not None:
        raise JournalEntryIsReversalError(
            f"entry {original.entry_number} is itself a reversal; cannot reverse it"
        )

    desc = description or f"Reversal of {original.entry_number}: {original.description}"

    reversal_lines = [
        JournalLineInput(
            account_id=line.account_id,
            debit=_to_decimal(line.credit),
            credit=_to_decimal(line.debit),
            line_number=line.line_number,
            memo=line.memo,
            division_id=line.division_id,
        )
        for line in original.lines
    ]

    reversal_entry = await post(
        JournalEntryInput(
            description=desc,
            posted_at=datetime.now(UTC),
            lines=reversal_lines,
        ),
        session=session,
        actor_user_id=actor_user_id,
        reversal_of_entry_id=original.id,
    )
    # reversal_of_entry_id is non-None so post() can't return an
    # ApprovalRequest here; narrow for the type checker.
    assert isinstance(reversal_entry, JournalEntry)

    # The PG immutability trigger explicitly allows this exact mutation
    # (OLD.is_reversed=false → NEW.is_reversed=true with every other
    # field unchanged). The spec calls for raw SQL for explicitness; we
    # use SQLAlchemy's typed UPDATE so the UUID parameter binds correctly
    # against both SQLite (32-char hex column) and PG (native uuid). The
    # OLD/NEW values seen by the trigger are identical either way.
    await session.execute(
        update(JournalEntry)
        .where(JournalEntry.id == original.id)
        .values(is_reversed=True)
        .execution_options(synchronize_session="fetch")
    )
    await session.flush()
    # Expire the cached attribute so a subsequent read sees the fresh
    # value.
    await session.refresh(original, ["is_reversed"])

    await _emit(
        session,
        event_type=accounting_events.TYPE_JOURNAL_ENTRY_REVERSED,
        aggregate_id=original.id,
        payload={
            "original_entry_id": str(original.id),
            "reversal_entry_id": str(reversal_entry.id),
            "reversal_entry_number": reversal_entry.entry_number,
        },
        actor_user_id=actor_user_id,
    )

    return reversal_entry


async def get(entry_id: uuid.UUID, *, session: AsyncSession) -> JournalEntry:
    return await _load_full(session, entry_id)


@dataclass
class JournalEntryPage:
    items: list[JournalEntry]
    next_cursor: str | None


async def list_entries(
    *,
    session: AsyncSession,
    account_id: uuid.UUID | None = None,
    posted_at_from: datetime | None = None,
    posted_at_to: datetime | None = None,
    cursor: str | None = None,
    limit: int = 50,
) -> JournalEntryPage:
    """List entries newest-first, paginated by ``(posted_at, entry_number)``.

    When ``account_id`` is supplied, results are filtered to entries that
    touch that account via a subquery on ``journal_line``.
    """
    stmt = select(JournalEntry).options(selectinload(JournalEntry.lines))
    if account_id is not None:
        stmt = stmt.where(
            JournalEntry.id.in_(
                select(JournalLine.entry_id).where(JournalLine.account_id == account_id)
            )
        )
    if posted_at_from is not None:
        stmt = stmt.where(JournalEntry.posted_at >= posted_at_from)
    if posted_at_to is not None:
        stmt = stmt.where(JournalEntry.posted_at <= posted_at_to)
    if cursor is not None:
        anchor_ts, anchor_number = _decode_cursor(cursor)
        # newer-first: walk DESC; the cursor is the last row of the
        # previous page, so we want rows strictly older than it.
        stmt = stmt.where(
            or_(
                JournalEntry.posted_at < anchor_ts,
                and_(
                    JournalEntry.posted_at == anchor_ts,
                    JournalEntry.entry_number < anchor_number,
                ),
            )
        )
    stmt = stmt.order_by(desc(JournalEntry.posted_at), desc(JournalEntry.entry_number)).limit(
        limit + 1
    )

    rows = list((await session.execute(stmt)).scalars().all())
    has_more = len(rows) > limit
    if has_more:
        rows = rows[:limit]
    next_cursor = (
        _encode_cursor(rows[-1].posted_at, rows[-1].entry_number) if (rows and has_more) else None
    )
    return JournalEntryPage(items=rows, next_cursor=next_cursor)


__all__ = [
    "AccountArchivedError",
    "AccountNotFoundError",
    "InvalidCursorError",
    "JournalEntriesServiceError",
    "JournalEntryAlreadyReversedError",
    "JournalEntryEmptyDescriptionError",
    "JournalEntryInput",
    "JournalEntryIsReversalError",
    "JournalEntryNotFoundError",
    "JournalEntryPage",
    "JournalEntryTooFewLinesError",
    "JournalEntryUnbalancedError",
    "JournalLineInput",
    "JournalLineInvalidError",
    "NoMatchingPeriodError",
    "PeriodNotOpenError",
    "get",
    "list_entries",
    "post",
    "reverse",
]
