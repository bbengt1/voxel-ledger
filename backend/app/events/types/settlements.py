"""Settlements event types (Phase 9.8, #160).

Marketplace settlement aggregate. A settlement carries the per-period
payout summary from a marketplace (Etsy / Amazon / Shopify / generic
CSV). Lines on a settlement carry the individual rows from the upload.

CRITICAL PII RULE
-----------------
``notes``, ``description``, ``external_order_id`` and ``external_txn_id``
MUST NEVER be whitelisted into audit excerpts. They may carry buyer
order ids, product names, and other operator / customer-supplied free
text. Excerpts whitelist only ``(settlement_number, channel_id,
period_end, payout_amount, line_count)`` — see
``app/projections/audit/excerpts.py``.
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict

from app.events.registry import register_event


class _SettlementsPayloadBase(BaseModel):
    model_config = ConfigDict(extra="forbid")


AGGREGATE_TYPE_SETTLEMENT: str = "settlement"


# --- Imported --------------------------------------------------------------


class SettlementImportedPayload(_SettlementsPayloadBase):
    settlement_id: uuid.UUID
    settlement_number: str
    channel_id: uuid.UUID
    period_end: str
    line_count: int
    gross_amount: str
    fee_amount: str
    refund_amount: str
    adjustment_amount: str
    payout_amount: str


# --- Cancelled --------------------------------------------------------------


class SettlementCancelledPayload(_SettlementsPayloadBase):
    settlement_id: uuid.UUID


# --- Matched + Posted (Phase 9.9, #161) ------------------------------------


class SettlementMatchedPayload(_SettlementsPayloadBase):
    settlement_id: uuid.UUID
    settlement_number: str
    matched_count: int
    unmatched_count: int
    ignored_count: int


class SettlementLineMatchedPayload(_SettlementsPayloadBase):
    settlement_id: uuid.UUID
    line_id: uuid.UUID
    line_kind: str
    matched_sale_id: uuid.UUID | None = None
    matched_refund_id: uuid.UUID | None = None
    match_strategy: str


class SettlementLineUnmatchedPayload(_SettlementsPayloadBase):
    settlement_id: uuid.UUID
    line_id: uuid.UUID


class SettlementLineIgnoredPayload(_SettlementsPayloadBase):
    settlement_id: uuid.UUID
    line_id: uuid.UUID


class SettlementPostedPayload(_SettlementsPayloadBase):
    settlement_id: uuid.UUID
    settlement_number: str
    channel_id: uuid.UUID
    journal_entry_id: uuid.UUID
    payout_amount: str
    fee_amount: str
    adjustment_amount: str
    clearing_credit: str


TYPE_SETTLEMENT_IMPORTED = "settlements.SettlementImported"
TYPE_SETTLEMENT_CANCELLED = "settlements.SettlementCancelled"
TYPE_SETTLEMENT_MATCHED = "settlements.SettlementMatched"
TYPE_SETTLEMENT_LINE_MATCHED = "settlements.SettlementLineMatched"
TYPE_SETTLEMENT_LINE_UNMATCHED = "settlements.SettlementLineUnmatched"
TYPE_SETTLEMENT_LINE_IGNORED = "settlements.SettlementLineIgnored"
TYPE_SETTLEMENT_POSTED = "settlements.SettlementPosted"


register_event(TYPE_SETTLEMENT_IMPORTED, SettlementImportedPayload)
register_event(TYPE_SETTLEMENT_CANCELLED, SettlementCancelledPayload)
register_event(TYPE_SETTLEMENT_MATCHED, SettlementMatchedPayload)
register_event(TYPE_SETTLEMENT_LINE_MATCHED, SettlementLineMatchedPayload)
register_event(TYPE_SETTLEMENT_LINE_UNMATCHED, SettlementLineUnmatchedPayload)
register_event(TYPE_SETTLEMENT_LINE_IGNORED, SettlementLineIgnoredPayload)
register_event(TYPE_SETTLEMENT_POSTED, SettlementPostedPayload)
