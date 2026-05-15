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


TYPE_JOURNAL_ENTRY_POSTED = "accounting.JournalEntryPosted"
TYPE_JOURNAL_ENTRY_REVERSED = "accounting.JournalEntryReversed"


register_event(TYPE_JOURNAL_ENTRY_POSTED, JournalEntryPostedPayload)
register_event(TYPE_JOURNAL_ENTRY_REVERSED, JournalEntryReversedPayload)
