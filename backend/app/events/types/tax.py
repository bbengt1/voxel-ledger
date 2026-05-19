"""Tax-profile event types (Phase 9.5, #157).

Aggregates: ``tax_profile`` (top-level) + ``tax_rate`` (nested).

CRITICAL PII RULE
-----------------
``notes`` on a tax profile is operator free-text and MUST NEVER be
whitelisted into the audit excerpt. The payload carries it for replay
but the audit denormalization stays strictly to
``(code, name, jurisdiction, is_reverse_charge)``. See
``app/projections/audit/excerpts.py``.
"""

from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.events.registry import register_event

AGGREGATE_TYPE_TAX_PROFILE: str = "tax_profile"
AGGREGATE_TYPE_TAX_RATE: str = "tax_rate"
AGGREGATE_TYPE_TAX_REMITTANCE: str = "tax_remittance"


class _TaxPayloadBase(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --- Tax profile ----------------------------------------------------------


class TaxProfileCreatedPayload(_TaxPayloadBase):
    tax_profile_id: uuid.UUID
    code: str
    name: str
    jurisdiction: str
    is_reverse_charge: bool
    is_active: bool
    notes: str | None = None


class TaxProfileUpdatedPayload(_TaxPayloadBase):
    tax_profile_id: uuid.UUID
    before: dict[str, Any]
    after: dict[str, Any]


class TaxProfileArchivedPayload(_TaxPayloadBase):
    tax_profile_id: uuid.UUID
    code: str
    name: str


# --- Tax rate -------------------------------------------------------------


class TaxRateCreatedPayload(_TaxPayloadBase):
    tax_rate_id: uuid.UUID
    profile_id: uuid.UUID
    ordinal: int
    name: str
    rate: str
    compound_on_previous: bool
    liability_account_id: uuid.UUID


class TaxRateUpdatedPayload(_TaxPayloadBase):
    tax_rate_id: uuid.UUID
    profile_id: uuid.UUID
    before: dict[str, Any]
    after: dict[str, Any]


class TaxRateRemovedPayload(_TaxPayloadBase):
    tax_rate_id: uuid.UUID
    profile_id: uuid.UUID
    ordinal: int


# --- Tax remittance (Phase 9.6, #158) -------------------------------------


class TaxRemittanceRecordedPayload(_TaxPayloadBase):
    remittance_id: uuid.UUID
    remittance_number: str
    profile_id: uuid.UUID
    period_start: str
    period_end: str
    amount_paid: str
    paid_on: str
    method: str
    reference_number: str | None = None
    bank_account_id: uuid.UUID
    journal_entry_id: uuid.UUID
    per_rate_allocations: list[dict[str, Any]]


class TaxRemittanceCancelledPayload(_TaxPayloadBase):
    remittance_id: uuid.UUID
    remittance_number: str
    original_journal_entry_id: uuid.UUID
    reversal_journal_entry_id: uuid.UUID


TYPE_TAX_PROFILE_CREATED = "tax.TaxProfileCreated"
TYPE_TAX_PROFILE_UPDATED = "tax.TaxProfileUpdated"
TYPE_TAX_PROFILE_ARCHIVED = "tax.TaxProfileArchived"
TYPE_TAX_RATE_CREATED = "tax.TaxRateCreated"
TYPE_TAX_RATE_UPDATED = "tax.TaxRateUpdated"
TYPE_TAX_RATE_REMOVED = "tax.TaxRateRemoved"
TYPE_TAX_REMITTANCE_RECORDED = "tax.TaxRemittanceRecorded"
TYPE_TAX_REMITTANCE_CANCELLED = "tax.TaxRemittanceCancelled"


register_event(TYPE_TAX_PROFILE_CREATED, TaxProfileCreatedPayload)
register_event(TYPE_TAX_PROFILE_UPDATED, TaxProfileUpdatedPayload)
register_event(TYPE_TAX_PROFILE_ARCHIVED, TaxProfileArchivedPayload)
register_event(TYPE_TAX_RATE_CREATED, TaxRateCreatedPayload)
register_event(TYPE_TAX_RATE_UPDATED, TaxRateUpdatedPayload)
register_event(TYPE_TAX_RATE_REMOVED, TaxRateRemovedPayload)
register_event(TYPE_TAX_REMITTANCE_RECORDED, TaxRemittanceRecordedPayload)
register_event(TYPE_TAX_REMITTANCE_CANCELLED, TaxRemittanceCancelledPayload)
