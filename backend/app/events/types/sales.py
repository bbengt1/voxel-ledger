"""Sales-bounded-context event types (Phase 6.1, #93).

The first sales aggregate is the ``sales_channel`` — a per-channel
configuration object (POS, marketplace, direct web, wholesale, other)
that owns its fee model and a couple of default GL account references.
Phase 6.2 adds the ``sale_order`` aggregate that consumes this config.

No secret-shaped fields exist on this aggregate today; the fee
percentages, flat fees, and account references are all configuration
metadata that the audit projection happily denormalizes.
"""

from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.events.registry import register_event

AGGREGATE_TYPE_SALES_CHANNEL: str = "sales_channel"


class _SalesPayloadBase(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --- Sales channels ---------------------------------------------------------


class SalesChannelCreatedPayload(_SalesPayloadBase):
    sales_channel_id: uuid.UUID
    name: str
    slug: str
    kind: str
    fee_model: str
    fee_percent: str | None = None
    fee_flat: str | None = None
    default_revenue_account_id: uuid.UUID | None = None
    default_fee_account_id: uuid.UUID | None = None
    external_id_format_hint: str | None = None


class SalesChannelUpdatedPayload(_SalesPayloadBase):
    sales_channel_id: uuid.UUID
    before: dict[str, Any]
    after: dict[str, Any]


class SalesChannelArchivedPayload(_SalesPayloadBase):
    sales_channel_id: uuid.UUID


class SalesChannelUnarchivedPayload(_SalesPayloadBase):
    sales_channel_id: uuid.UUID


TYPE_SALES_CHANNEL_CREATED = "sales.SalesChannelCreated"
TYPE_SALES_CHANNEL_UPDATED = "sales.SalesChannelUpdated"
TYPE_SALES_CHANNEL_ARCHIVED = "sales.SalesChannelArchived"
TYPE_SALES_CHANNEL_UNARCHIVED = "sales.SalesChannelUnarchived"


register_event(TYPE_SALES_CHANNEL_CREATED, SalesChannelCreatedPayload)
register_event(TYPE_SALES_CHANNEL_UPDATED, SalesChannelUpdatedPayload)
register_event(TYPE_SALES_CHANNEL_ARCHIVED, SalesChannelArchivedPayload)
register_event(TYPE_SALES_CHANNEL_UNARCHIVED, SalesChannelUnarchivedPayload)
