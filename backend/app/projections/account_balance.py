"""Projection: per-account running ``total_debits`` / ``total_credits``.

Subscribes to ``accounting.JournalEntryPosted`` and applies the upsert::

    INSERT ... ON CONFLICT (account_id) DO UPDATE
    SET total_debits  = account_balance.total_debits  + EXCLUDED.total_debits,
        total_credits = account_balance.total_credits + EXCLUDED.total_credits,
        updated_at    = now()

Decimal arithmetic only. The net signed balance is computed at READ
time by the API layer using the account's natural sign — assets and
expenses are debit-normal; liabilities, equity, and revenue are
credit-normal. We do not store a signed ``balance`` column because the
sign is a property of the account, not of the balance row.

JournalEntryReversed is a no-op for balance math
------------------------------------------------
The reversal flow in ``app.services.journal_entries.reverse`` posts a
brand-new entry with swapped debits/credits. That post emits its own
``JournalEntryPosted`` event, which the handler below has already
applied, cancelling the original's effect on every touched account.
The trailing ``JournalEntryReversed`` event is informational for the
audit log; treating it as a no-op here keeps the math correct (a second
swap would double-cancel). A dedicated test asserts this behavior.

Replay parity
-------------
INSERT-with-conflict-summation is associative and commutative on
per-event deltas. Truncating ``account_balance``, resetting the
projection cursor, and replaying from position 0 reproduces the same
totals byte-for-byte.
"""

from __future__ import annotations

import uuid
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.events.types.accounting import (
    TYPE_JOURNAL_ENTRY_POSTED,
    TYPE_JOURNAL_ENTRY_REVERSED,
)
from app.models.account_balance import AccountBalance
from app.models.event import Event
from app.projections.registry import projection

HANDLER_NAME = "account_balance"
READ_MODEL_TABLES: tuple[str, ...] = ("account_balance",)

_QUANTUM = Decimal("0.000001")


def _to_decimal(value: object) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _to_uuid(value: object) -> uuid.UUID:
    if isinstance(value, uuid.UUID):
        return value
    return uuid.UUID(str(value))


def _aggregate_lines(payload: dict) -> dict[uuid.UUID, tuple[Decimal, Decimal]]:
    """Group line debits/credits by account so we issue one upsert per
    account per entry — multi-line entries that touch the same account
    twice still produce a single round-trip per account."""
    totals: dict[uuid.UUID, tuple[Decimal, Decimal]] = {}
    for line in payload.get("lines", []) or []:
        account_id = _to_uuid(line["account_id"])
        debit = _to_decimal(line.get("debit", "0")).quantize(_QUANTUM, rounding=ROUND_HALF_UP)
        credit = _to_decimal(line.get("credit", "0")).quantize(_QUANTUM, rounding=ROUND_HALF_UP)
        prev_d, prev_c = totals.get(account_id, (Decimal("0"), Decimal("0")))
        totals[account_id] = (prev_d + debit, prev_c + credit)
    return totals


@projection(
    event_type=TYPE_JOURNAL_ENTRY_POSTED,
    name=HANDLER_NAME,
    read_model_tables=READ_MODEL_TABLES,
)
async def project_journal_entry_posted(event: Event, session: AsyncSession) -> None:
    """Apply one ``accounting.JournalEntryPosted`` event.

    Upserts each touched ``account_balance`` row with the line deltas.
    """
    payload = event.payload or {}
    totals = _aggregate_lines(payload)
    if not totals:
        return

    dialect = session.bind.dialect.name if session.bind is not None else "sqlite"
    insert_fn = pg_insert if dialect == "postgresql" else sqlite_insert

    for account_id, (debit_delta, credit_delta) in totals.items():
        stmt = insert_fn(AccountBalance).values(
            account_id=account_id,
            total_debits=debit_delta,
            total_credits=credit_delta,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["account_id"],
            set_={
                "total_debits": AccountBalance.total_debits + stmt.excluded.total_debits,
                "total_credits": AccountBalance.total_credits + stmt.excluded.total_credits,
                "updated_at": func.now(),
            },
        )
        await session.execute(stmt)
    await session.flush()


@projection(
    event_type=TYPE_JOURNAL_ENTRY_REVERSED,
    name=f"{HANDLER_NAME}_reversed_noop",
    read_model_tables=READ_MODEL_TABLES,
)
async def project_journal_entry_reversed(event: Event, session: AsyncSession) -> None:
    """No-op for balance math.

    The reversal entry's ``JournalEntryPosted`` event has already
    applied the cancelling debits/credits. This handler only exists so
    the registry knows the read-model table is subscribed to the event
    type (and so a reader of the registry can see the intentional
    no-op rather than wondering why nothing is registered).
    """
    return None
