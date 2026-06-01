"""Production-bounded-context event types (Phase 5.1).

The production domain owns printers and their attached cameras. CRUD
events are catalog-style: aside from the wildcard audit-log projection,
no other projection consumes them today.

**Secret handling.** The ``moonraker_api_key`` and ``password_secret``
fields are the only secret-shaped data on these aggregates. They are
NEVER carried in any event payload — neither the create event nor the
update-diff event. The service layer substitutes the sentinel ``"***"``
into the ``before``/``after`` diffs before emitting an update event, so
the on-disk event log never contains the secret. A regression test
guards this invariant.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.events.registry import register_event

AGGREGATE_TYPE_PRINTER: str = "printer"
AGGREGATE_TYPE_CAMERA: str = "camera"
AGGREGATE_TYPE_JOB: str = "job"
AGGREGATE_TYPE_PLATE: str = "plate"
AGGREGATE_TYPE_PRODUCTION_ORDER: str = "production_order"


class _ProductionPayloadBase(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --- Printers ----------------------------------------------------------------


class PrinterCreatedPayload(_ProductionPayloadBase):
    printer_id: uuid.UUID
    name: str
    slug: str
    printer_type: str


class PrinterUpdatedPayload(_ProductionPayloadBase):
    """Update diff. ``moonraker_api_key`` always appears as ``"***"``
    in both before/after when it changed — the real secret never crosses
    the event boundary."""

    printer_id: uuid.UUID
    before: dict[str, Any]
    after: dict[str, Any]


class PrinterArchivedPayload(_ProductionPayloadBase):
    printer_id: uuid.UUID


class PrinterUnarchivedPayload(_ProductionPayloadBase):
    printer_id: uuid.UUID


TYPE_PRINTER_CREATED = "production.PrinterCreated"
TYPE_PRINTER_UPDATED = "production.PrinterUpdated"
TYPE_PRINTER_ARCHIVED = "production.PrinterArchived"
TYPE_PRINTER_UNARCHIVED = "production.PrinterUnarchived"


register_event(TYPE_PRINTER_CREATED, PrinterCreatedPayload)
register_event(TYPE_PRINTER_UPDATED, PrinterUpdatedPayload)
register_event(TYPE_PRINTER_ARCHIVED, PrinterArchivedPayload)
register_event(TYPE_PRINTER_UNARCHIVED, PrinterUnarchivedPayload)


# --- Cameras -----------------------------------------------------------------


class CameraConfiguredPayload(_ProductionPayloadBase):
    """Set/replace a camera config. ``username`` is intentionally omitted
    so we don't denormalize a plausible login identifier into the event
    log. ``password_secret`` is omitted for obvious reasons."""

    camera_id: uuid.UUID
    printer_id: uuid.UUID
    kind: str
    snapshot_url: str


class CameraUpdatedPayload(_ProductionPayloadBase):
    """Update diff. ``password_secret`` always appears as ``"***"`` in
    both before/after when it changed — the real secret never crosses
    the event boundary."""

    camera_id: uuid.UUID
    printer_id: uuid.UUID
    before: dict[str, Any]
    after: dict[str, Any]


class CameraDeletedPayload(_ProductionPayloadBase):
    camera_id: uuid.UUID
    printer_id: uuid.UUID


TYPE_CAMERA_CONFIGURED = "production.CameraConfigured"
TYPE_CAMERA_UPDATED = "production.CameraUpdated"
TYPE_CAMERA_DELETED = "production.CameraDeleted"


register_event(TYPE_CAMERA_CONFIGURED, CameraConfiguredPayload)
register_event(TYPE_CAMERA_UPDATED, CameraUpdatedPayload)
register_event(TYPE_CAMERA_DELETED, CameraDeletedPayload)


# --- Jobs + plates (Phase 5.2) ---------------------------------------------


class JobPlateSummary(_ProductionPayloadBase):
    """Embedded plate descriptor for ``JobCreated``."""

    plate_id: uuid.UUID
    name: str
    plate_number: int
    parts_per_set: int
    print_minutes: int
    print_hours_setup_minutes: int


class JobCreatedPayload(_ProductionPayloadBase):
    job_id: uuid.UUID
    job_number: str
    # Epic #267 Phase 4: a job targets a part OR (legacy) a product.
    product_id: uuid.UUID | None = None
    part_id: uuid.UUID | None = None
    quantity_ordered: int
    plates: list[JobPlateSummary]


class JobUpdatedPayload(_ProductionPayloadBase):
    job_id: uuid.UUID
    before: dict[str, Any]
    after: dict[str, Any]


class JobStateChangePayload(_ProductionPayloadBase):
    job_id: uuid.UUID


class PlateAssignedPayload(_ProductionPayloadBase):
    plate_id: uuid.UUID
    job_id: uuid.UUID
    printer_id: uuid.UUID


class PlateUnassignedPayload(_ProductionPayloadBase):
    plate_id: uuid.UUID
    job_id: uuid.UUID
    printer_id: uuid.UUID


class PlateMaterialConsumption(_ProductionPayloadBase):
    material_id: uuid.UUID
    grams: str


class PlateRunRecordedPayload(_ProductionPayloadBase):
    plate_id: uuid.UUID
    job_id: uuid.UUID
    new_runs_completed: int
    materials_consumed: list[PlateMaterialConsumption]


TYPE_JOB_CREATED = "production.JobCreated"
TYPE_JOB_UPDATED = "production.JobUpdated"
TYPE_JOB_SUBMITTED = "production.JobSubmitted"
TYPE_JOB_STARTED = "production.JobStarted"
TYPE_JOB_COMPLETED = "production.JobCompleted"
TYPE_JOB_CANCELLED = "production.JobCancelled"
TYPE_PLATE_ASSIGNED = "production.PlateAssigned"
TYPE_PLATE_UNASSIGNED = "production.PlateUnassigned"
TYPE_PLATE_RUN_RECORDED = "production.PlateRunRecorded"


register_event(TYPE_JOB_CREATED, JobCreatedPayload)
register_event(TYPE_JOB_UPDATED, JobUpdatedPayload)
register_event(TYPE_JOB_SUBMITTED, JobStateChangePayload)
register_event(TYPE_JOB_STARTED, JobStateChangePayload)
register_event(TYPE_JOB_COMPLETED, JobStateChangePayload)
register_event(TYPE_JOB_CANCELLED, JobStateChangePayload)
register_event(TYPE_PLATE_ASSIGNED, PlateAssignedPayload)
register_event(TYPE_PLATE_UNASSIGNED, PlateUnassignedPayload)
register_event(TYPE_PLATE_RUN_RECORDED, PlateRunRecordedPayload)


# --- Printer history (Phase 5.4) ---------------------------------------------
#
# The lazy printer monitor (``app.services.printer_monitor``) appends one
# ``PrinterHistoryEventRecorded`` per state transition observed on the
# Moonraker feed plus synthetic ``connected``/``disconnected`` rows
# derived from socket liveness. The event ``details`` blob is opaque
# scratch metadata (e.g. ``{"file": "thing.gcode", "progress": 0.42}``)
# and is intentionally NOT whitelisted into the audit excerpt — only
# ``event_kind`` / ``printer_id`` / ``occurred_at`` are.


class PrinterHistoryEventRecordedPayload(_ProductionPayloadBase):
    event_id: uuid.UUID
    printer_id: uuid.UUID
    event_kind: str
    occurred_at: datetime
    details: dict[str, Any] | None = None


TYPE_PRINTER_HISTORY_EVENT_RECORDED = "production.PrinterHistoryEventRecorded"

register_event(TYPE_PRINTER_HISTORY_EVENT_RECORDED, PrinterHistoryEventRecordedPayload)


# --- Production orders (Phase 5.5) -------------------------------------------


class ProductionOrderCreatedPayload(_ProductionPayloadBase):
    production_order_id: uuid.UUID
    order_number: str
    name: str
    state: str
    priority: int
    due_at: datetime | None = None


class ProductionOrderUpdatedPayload(_ProductionPayloadBase):
    production_order_id: uuid.UUID
    before: dict[str, Any]
    after: dict[str, Any]


class ProductionOrderStateChangePayload(_ProductionPayloadBase):
    production_order_id: uuid.UUID


class JobAddedToOrderPayload(_ProductionPayloadBase):
    production_order_id: uuid.UUID
    job_id: uuid.UUID
    display_order: int


class JobRemovedFromOrderPayload(_ProductionPayloadBase):
    production_order_id: uuid.UUID
    job_id: uuid.UUID


TYPE_PRODUCTION_ORDER_CREATED = "production.ProductionOrderCreated"
TYPE_PRODUCTION_ORDER_UPDATED = "production.ProductionOrderUpdated"
TYPE_PRODUCTION_ORDER_ACTIVATED = "production.ProductionOrderActivated"
TYPE_PRODUCTION_ORDER_COMPLETED = "production.ProductionOrderCompleted"
TYPE_PRODUCTION_ORDER_ARCHIVED = "production.ProductionOrderArchived"
TYPE_JOB_ADDED_TO_ORDER = "production.JobAddedToOrder"
TYPE_JOB_REMOVED_FROM_ORDER = "production.JobRemovedFromOrder"


register_event(TYPE_PRODUCTION_ORDER_CREATED, ProductionOrderCreatedPayload)
register_event(TYPE_PRODUCTION_ORDER_UPDATED, ProductionOrderUpdatedPayload)
register_event(TYPE_PRODUCTION_ORDER_ACTIVATED, ProductionOrderStateChangePayload)
register_event(TYPE_PRODUCTION_ORDER_COMPLETED, ProductionOrderStateChangePayload)
register_event(TYPE_PRODUCTION_ORDER_ARCHIVED, ProductionOrderStateChangePayload)
register_event(TYPE_JOB_ADDED_TO_ORDER, JobAddedToOrderPayload)
register_event(TYPE_JOB_REMOVED_FROM_ORDER, JobRemovedFromOrderPayload)
