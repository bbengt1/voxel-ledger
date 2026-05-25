"""Accounting-bounded-context event types (Phase 4.1).

Phase 4.1 (#64) introduces the chart-of-accounts aggregate. Future
Phase 4.x issues add journal entries, postings, and period close.

Payloads use ``extra="forbid"`` so a stray key trips registration
immediately rather than silently leaking into the event log.
"""

from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.events.registry import register_event

# Account aggregate. Each chart-of-accounts row is its own aggregate.
AGGREGATE_TYPE_ACCOUNT: str = "account"

# Journal-entry aggregate. Each posted entry is its own aggregate; lines
# do not have aggregate identity of their own.
AGGREGATE_TYPE_JOURNAL_ENTRY: str = "journal_entry"


class _AccountingPayloadBase(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AccountCreatedPayload(_AccountingPayloadBase):
    account_id: uuid.UUID
    code: str
    name: str
    type: str
    parent_account_id: uuid.UUID | None = None


class AccountUpdatedPayload(_AccountingPayloadBase):
    account_id: uuid.UUID
    before: dict[str, Any]
    after: dict[str, Any]


class AccountArchivedPayload(_AccountingPayloadBase):
    account_id: uuid.UUID


class AccountUnarchivedPayload(_AccountingPayloadBase):
    account_id: uuid.UUID


TYPE_ACCOUNT_CREATED = "accounting.AccountCreated"
TYPE_ACCOUNT_UPDATED = "accounting.AccountUpdated"
TYPE_ACCOUNT_ARCHIVED = "accounting.AccountArchived"
TYPE_ACCOUNT_UNARCHIVED = "accounting.AccountUnarchived"


register_event(TYPE_ACCOUNT_CREATED, AccountCreatedPayload)
register_event(TYPE_ACCOUNT_UPDATED, AccountUpdatedPayload)
register_event(TYPE_ACCOUNT_ARCHIVED, AccountArchivedPayload)
register_event(TYPE_ACCOUNT_UNARCHIVED, AccountUnarchivedPayload)


# --- Journal entries (Phase 4.2) ---
#
# Decimals are serialized as canonical strings (``Decimal.to_eng_string()``)
# so the projection can recover exact values without float drift. UUIDs are
# serialized as strings. ``extra="forbid"`` on every payload model so a
# stray key trips registration immediately.


class JournalLinePayload(_AccountingPayloadBase):
    account_id: uuid.UUID
    debit: str
    credit: str
    line_number: int
    memo: str | None = None
    # Optional second analytical dimension (Phase 4.5, #68). Older
    # events written before Phase 4.5 simply omit the key — the default
    # keeps replay parity.
    division_id: uuid.UUID | None = None


class JournalEntryPostedPayload(_AccountingPayloadBase):
    entry_id: uuid.UUID
    entry_number: str
    posted_at: str  # ISO-8601, tz-aware
    period_id: uuid.UUID | None = None
    description: str
    source_event_id: uuid.UUID | None = None
    actor_user_id: uuid.UUID | None = None
    reversal_of_entry_id: uuid.UUID | None = None
    lines: list[JournalLinePayload]


class JournalEntryReversedPayload(_AccountingPayloadBase):
    original_entry_id: uuid.UUID
    reversal_entry_id: uuid.UUID
    reversal_entry_number: str
    # True when the original being reversed was itself a reversal — an
    # auditor's flag, not a workflow change. Defaults False so existing
    # backfill / replay paths don't have to set it.
    reversal_of_reversal: bool = False


TYPE_JOURNAL_ENTRY_POSTED = "accounting.JournalEntryPosted"
TYPE_JOURNAL_ENTRY_REVERSED = "accounting.JournalEntryReversed"


register_event(TYPE_JOURNAL_ENTRY_POSTED, JournalEntryPostedPayload)
register_event(TYPE_JOURNAL_ENTRY_REVERSED, JournalEntryReversedPayload)


# --- Accounting periods (Phase 4.3) ---
#
# Each accounting period is its own aggregate. Dates serialize as ISO
# strings; UUIDs serialize as strings. ``extra="forbid"`` keeps the
# payload contract tight.

AGGREGATE_TYPE_ACCOUNTING_PERIOD: str = "accounting_period"


class PeriodCreatedPayload(_AccountingPayloadBase):
    period_id: uuid.UUID
    name: str
    start_date: str  # ISO date
    end_date: str  # ISO date


class PeriodUpdatedPayload(_AccountingPayloadBase):
    period_id: uuid.UUID
    before: dict[str, Any]
    after: dict[str, Any]


class PeriodClosedPayload(_AccountingPayloadBase):
    period_id: uuid.UUID
    closed_by_user_id: uuid.UUID | None = None


class PeriodReopenedPayload(_AccountingPayloadBase):
    period_id: uuid.UUID
    reopened_by_user_id: uuid.UUID | None = None


class PeriodLockedPayload(_AccountingPayloadBase):
    period_id: uuid.UUID
    locked_by_user_id: uuid.UUID | None = None


TYPE_PERIOD_CREATED = "accounting.PeriodCreated"
TYPE_PERIOD_UPDATED = "accounting.PeriodUpdated"
TYPE_PERIOD_CLOSED = "accounting.PeriodClosed"
TYPE_PERIOD_REOPENED = "accounting.PeriodReopened"
TYPE_PERIOD_LOCKED = "accounting.PeriodLocked"


register_event(TYPE_PERIOD_CREATED, PeriodCreatedPayload)
register_event(TYPE_PERIOD_UPDATED, PeriodUpdatedPayload)
register_event(TYPE_PERIOD_CLOSED, PeriodClosedPayload)
register_event(TYPE_PERIOD_REOPENED, PeriodReopenedPayload)
register_event(TYPE_PERIOD_LOCKED, PeriodLockedPayload)


# --- Divisions + budgets (Phase 4.5) ---
#
# Divisions are a light second analytical dimension on journal lines.
# Budgets are slots keyed by ``(account_id, division_id, period_id)`` —
# ``division_id`` may be NULL for the catch-all budget per account/period.
# Decimal amounts on budgets serialize as canonical strings.

AGGREGATE_TYPE_DIVISION: str = "division"
AGGREGATE_TYPE_BUDGET: str = "budget"


class DivisionCreatedPayload(_AccountingPayloadBase):
    division_id: uuid.UUID
    name: str
    code: str


class DivisionUpdatedPayload(_AccountingPayloadBase):
    division_id: uuid.UUID
    before: dict[str, Any]
    after: dict[str, Any]


class DivisionArchivedPayload(_AccountingPayloadBase):
    division_id: uuid.UUID


class DivisionUnarchivedPayload(_AccountingPayloadBase):
    division_id: uuid.UUID


class BudgetSetPayload(_AccountingPayloadBase):
    account_id: uuid.UUID
    division_id: uuid.UUID | None = None
    period_id: uuid.UUID
    old_amount: str | None = None
    new_amount: str


class BudgetUnsetPayload(_AccountingPayloadBase):
    account_id: uuid.UUID
    division_id: uuid.UUID | None = None
    period_id: uuid.UUID


TYPE_DIVISION_CREATED = "accounting.DivisionCreated"
TYPE_DIVISION_UPDATED = "accounting.DivisionUpdated"
TYPE_DIVISION_ARCHIVED = "accounting.DivisionArchived"
TYPE_DIVISION_UNARCHIVED = "accounting.DivisionUnarchived"
TYPE_BUDGET_SET = "accounting.BudgetSet"
TYPE_BUDGET_UNSET = "accounting.BudgetUnset"


register_event(TYPE_DIVISION_CREATED, DivisionCreatedPayload)
register_event(TYPE_DIVISION_UPDATED, DivisionUpdatedPayload)
register_event(TYPE_DIVISION_ARCHIVED, DivisionArchivedPayload)
register_event(TYPE_DIVISION_UNARCHIVED, DivisionUnarchivedPayload)
register_event(TYPE_BUDGET_SET, BudgetSetPayload)
register_event(TYPE_BUDGET_UNSET, BudgetUnsetPayload)
