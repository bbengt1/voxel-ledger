"""Banking-bounded-context event types (Phase 8.9, #136).

Aggregates landing here:

* ``bank_import_mapping`` — operator-defined CSV column maps.
* ``bank_import_run`` — a single import action's summary.
* ``bank_transaction`` — individual parsed rows (we do NOT emit per-row
  events; the run-level ``ImportRunCompleted`` carries summary counts).

PII RULE
--------
``notes``, mapping ``column_map`` contents, and bank-transaction
``description`` / ``memo`` MUST NEVER be whitelisted into the audit
excerpt. Counts, filename, and IDs are the only fields safe to surface.
See ``app/projections/audit/excerpts.py``.
"""

from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.events.registry import register_event

AGGREGATE_TYPE_BANK_IMPORT_MAPPING: str = "bank_import_mapping"
AGGREGATE_TYPE_BANK_IMPORT_RUN: str = "bank_import_run"
AGGREGATE_TYPE_BANK_TRANSACTION: str = "bank_transaction"
AGGREGATE_TYPE_BANK_MATCH_RULE: str = "bank_match_rule"


class _BankingPayloadBase(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --- Mappings --------------------------------------------------------------


class MappingCreatedPayload(_BankingPayloadBase):
    mapping_id: uuid.UUID
    account_id: uuid.UUID
    name: str
    file_kind: str
    amount_sign: str
    delimiter: str
    has_header: bool
    encoding: str
    date_format: str | None = None
    column_map: dict[str, Any] = {}
    notes: str | None = None


class MappingUpdatedPayload(_BankingPayloadBase):
    mapping_id: uuid.UUID
    before: dict[str, Any]
    after: dict[str, Any]


class MappingDeactivatedPayload(_BankingPayloadBase):
    mapping_id: uuid.UUID
    account_id: uuid.UUID
    name: str


TYPE_MAPPING_CREATED = "banking.MappingCreated"
TYPE_MAPPING_UPDATED = "banking.MappingUpdated"
TYPE_MAPPING_DEACTIVATED = "banking.MappingDeactivated"


register_event(TYPE_MAPPING_CREATED, MappingCreatedPayload)
register_event(TYPE_MAPPING_UPDATED, MappingUpdatedPayload)
register_event(TYPE_MAPPING_DEACTIVATED, MappingDeactivatedPayload)


# --- Import runs -----------------------------------------------------------


class ImportRunStartedPayload(_BankingPayloadBase):
    run_id: uuid.UUID
    account_id: uuid.UUID
    mapping_id: uuid.UUID | None = None
    filename: str
    file_kind: str


class ImportRunCompletedPayload(_BankingPayloadBase):
    run_id: uuid.UUID
    account_id: uuid.UUID
    mapping_id: uuid.UUID | None = None
    filename: str
    row_count: int
    inserted_count: int
    duplicate_count: int
    error_count: int


class ImportRunFailedPayload(_BankingPayloadBase):
    run_id: uuid.UUID | None = None
    account_id: uuid.UUID
    filename: str
    reason: str


TYPE_IMPORT_RUN_STARTED = "banking.ImportRunStarted"
TYPE_IMPORT_RUN_COMPLETED = "banking.ImportRunCompleted"
TYPE_IMPORT_RUN_FAILED = "banking.ImportRunFailed"


register_event(TYPE_IMPORT_RUN_STARTED, ImportRunStartedPayload)
register_event(TYPE_IMPORT_RUN_COMPLETED, ImportRunCompletedPayload)
register_event(TYPE_IMPORT_RUN_FAILED, ImportRunFailedPayload)


# --- Match rules (Phase 8.10, #137) ----------------------------------------


class MatchRuleCreatedPayload(_BankingPayloadBase):
    rule_id: uuid.UUID
    account_id: uuid.UUID | None = None
    priority: int
    match_kind: str
    match_field: str
    match_value: str
    action_kind: str
    debit_account_id: uuid.UUID | None = None
    credit_account_id: uuid.UUID | None = None
    min_amount: str | None = None
    max_amount: str | None = None
    description_template: str | None = None
    notes: str | None = None


class MatchRuleUpdatedPayload(_BankingPayloadBase):
    rule_id: uuid.UUID
    before: dict[str, Any]
    after: dict[str, Any]


class MatchRuleDeactivatedPayload(_BankingPayloadBase):
    rule_id: uuid.UUID


TYPE_MATCH_RULE_CREATED = "banking.MatchRuleCreated"
TYPE_MATCH_RULE_UPDATED = "banking.MatchRuleUpdated"
TYPE_MATCH_RULE_DEACTIVATED = "banking.MatchRuleDeactivated"


register_event(TYPE_MATCH_RULE_CREATED, MatchRuleCreatedPayload)
register_event(TYPE_MATCH_RULE_UPDATED, MatchRuleUpdatedPayload)
register_event(TYPE_MATCH_RULE_DEACTIVATED, MatchRuleDeactivatedPayload)


# --- Bank transaction match-state transitions ------------------------------


class BankTransactionAutoMatchedPayload(_BankingPayloadBase):
    transaction_id: uuid.UUID
    rule_id: uuid.UUID
    journal_entry_id: uuid.UUID
    amount: str


class BankTransactionManuallyMatchedPayload(_BankingPayloadBase):
    transaction_id: uuid.UUID
    journal_entry_id: uuid.UUID
    journal_line_id: uuid.UUID


class BankTransactionUnmatchedPayload(_BankingPayloadBase):
    transaction_id: uuid.UUID
    previous_journal_line_id: uuid.UUID | None = None


class BankTransactionIgnoredPayload(_BankingPayloadBase):
    transaction_id: uuid.UUID
    rule_id: uuid.UUID | None = None


class BankTransactionFlaggedForReviewPayload(_BankingPayloadBase):
    transaction_id: uuid.UUID
    rule_id: uuid.UUID


TYPE_BANK_TRANSACTION_AUTO_MATCHED = "banking.BankTransactionAutoMatched"
TYPE_BANK_TRANSACTION_MANUALLY_MATCHED = "banking.BankTransactionManuallyMatched"
TYPE_BANK_TRANSACTION_UNMATCHED = "banking.BankTransactionUnmatched"
TYPE_BANK_TRANSACTION_IGNORED = "banking.BankTransactionIgnored"
TYPE_BANK_TRANSACTION_FLAGGED_FOR_REVIEW = "banking.BankTransactionFlaggedForReview"


register_event(TYPE_BANK_TRANSACTION_AUTO_MATCHED, BankTransactionAutoMatchedPayload)
register_event(TYPE_BANK_TRANSACTION_MANUALLY_MATCHED, BankTransactionManuallyMatchedPayload)
register_event(TYPE_BANK_TRANSACTION_UNMATCHED, BankTransactionUnmatchedPayload)
register_event(TYPE_BANK_TRANSACTION_IGNORED, BankTransactionIgnoredPayload)
register_event(TYPE_BANK_TRANSACTION_FLAGGED_FOR_REVIEW, BankTransactionFlaggedForReviewPayload)
