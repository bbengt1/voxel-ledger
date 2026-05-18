"""Accounting-assets event types (Phase 9.1, #153).

Aggregate ``fixed_asset`` covers BOTH tangible and intangible assets in
a single table; intangible is just a flavor of the same kind column.

CRITICAL PII RULE
-----------------
``notes`` MUST NEVER be whitelisted into audit excerpts. Payloads carry
it for replay but the audit denormalization stays strictly to
``asset_number``, ``name``, ``kind``, ``asset_class``, and
``acquisition_cost``. See
``app/projections/audit/excerpts.py``.
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict

from app.events.registry import register_event


class _AssetsPayloadBase(BaseModel):
    model_config = ConfigDict(extra="forbid")


AGGREGATE_TYPE_FIXED_ASSET: str = "fixed_asset"


# --- Created / Updated -----------------------------------------------------


class AssetCreatedPayload(_AssetsPayloadBase):
    asset_id: uuid.UUID
    asset_number: str
    name: str
    kind: str
    asset_class: str
    acquisition_cost: str
    useful_life_months: int


class AssetUpdatedPayload(_AssetsPayloadBase):
    asset_id: uuid.UUID
    before: dict
    after: dict


# --- Acquired (posts the JE inside the same TX) -----------------------------


class AssetAcquiredPayload(_AssetsPayloadBase):
    asset_id: uuid.UUID
    asset_number: str
    acquisition_cost: str
    journal_entry_id: uuid.UUID | None = None
    contra_account_id: uuid.UUID | None = None
    vendor_id: uuid.UUID | None = None
    acquisition_bill_id: uuid.UUID | None = None
    acquired_on: str


# --- Disposed (Phase 9.4 will populate) -------------------------------------


class AssetDisposedPayload(_AssetsPayloadBase):
    asset_id: uuid.UUID
    disposed_on: str
    kind: str


# --- Written off (reserved) -------------------------------------------------


class AssetWrittenOffPayload(_AssetsPayloadBase):
    asset_id: uuid.UUID
    written_off_on: str
    reason: str | None = None


# --- Depreciation schedule (Phase 9.2, #154) -------------------------------


AGGREGATE_TYPE_DEPRECIATION_SCHEDULE: str = "depreciation_schedule"


class DepreciationScheduleGeneratedPayload(_AssetsPayloadBase):
    asset_id: uuid.UUID
    total_entries: int
    total_depreciation: str
    method: str


class DepreciationScheduleRecomputedPayload(_AssetsPayloadBase):
    asset_id: uuid.UUID
    from_period_index: int
    total_recomputed: int


TYPE_ASSET_CREATED = "acc.AssetCreated"
TYPE_ASSET_UPDATED = "acc.AssetUpdated"
TYPE_ASSET_ACQUIRED = "acc.AssetAcquired"
TYPE_ASSET_DISPOSED = "acc.AssetDisposed"
TYPE_ASSET_WRITTEN_OFF = "acc.AssetWrittenOff"
TYPE_DEPRECIATION_SCHEDULE_GENERATED = "acc.DepreciationScheduleGenerated"
TYPE_DEPRECIATION_SCHEDULE_RECOMPUTED = "acc.DepreciationScheduleRecomputed"


register_event(TYPE_ASSET_CREATED, AssetCreatedPayload)
register_event(TYPE_ASSET_UPDATED, AssetUpdatedPayload)
register_event(TYPE_ASSET_ACQUIRED, AssetAcquiredPayload)
register_event(TYPE_ASSET_DISPOSED, AssetDisposedPayload)
register_event(TYPE_ASSET_WRITTEN_OFF, AssetWrittenOffPayload)
register_event(TYPE_DEPRECIATION_SCHEDULE_GENERATED, DepreciationScheduleGeneratedPayload)
register_event(TYPE_DEPRECIATION_SCHEDULE_RECOMPUTED, DepreciationScheduleRecomputedPayload)
