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


TYPE_SETTLEMENT_IMPORTED = "settlements.SettlementImported"
TYPE_SETTLEMENT_CANCELLED = "settlements.SettlementCancelled"


register_event(TYPE_SETTLEMENT_IMPORTED, SettlementImportedPayload)
register_event(TYPE_SETTLEMENT_CANCELLED, SettlementCancelledPayload)
