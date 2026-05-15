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
