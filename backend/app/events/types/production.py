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
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.events.registry import register_event

AGGREGATE_TYPE_PRINTER: str = "printer"
AGGREGATE_TYPE_CAMERA: str = "camera"


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
