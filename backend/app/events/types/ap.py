"""AP-bounded-context event types (Phase 8.1, #128).

Aggregates landing here:

* ``vendor`` (Phase 8.1) — the AP-side subject identity. Created /
  updated / archived / unarchived events, plus the nested contact CRUD.

CRITICAL PII RULE
-----------------
``primary_email``, ``phone``, ``billing_address``, ``shipping_address``,
``tax_id``, and ``notes`` MUST NEVER be whitelisted into the audit
excerpt. The payload carries them so the event log can reconstruct the
vendor, but the audit denormalization keeps strictly to
``vendor_number`` and ``display_name``. See
``app/projections/audit/excerpts.py``.
"""

from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.events.registry import register_event

AGGREGATE_TYPE_VENDOR: str = "vendor"
AGGREGATE_TYPE_VENDOR_CONTACT: str = "vendor_contact"


class _APPayloadBase(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --- Vendors ---------------------------------------------------------------


class VendorCreatedPayload(_APPayloadBase):
    vendor_id: uuid.UUID
    vendor_number: str
    display_name: str
    legal_name: str | None = None
    primary_email: str | None = None
    phone: str | None = None
    payment_terms_days: int
    default_expense_account_id: uuid.UUID | None = None
    default_ap_account_id: uuid.UUID | None = None
    tax_id: str | None = None
    is_1099_vendor: bool = False
    state: str


class VendorUpdatedPayload(_APPayloadBase):
    vendor_id: uuid.UUID
    before: dict[str, Any]
    after: dict[str, Any]


class VendorArchivedPayload(_APPayloadBase):
    vendor_id: uuid.UUID


class VendorUnarchivedPayload(_APPayloadBase):
    vendor_id: uuid.UUID


class VendorContactAddedPayload(_APPayloadBase):
    vendor_id: uuid.UUID
    contact_id: uuid.UUID
    name: str
    role_label: str | None = None
    is_primary: bool


class VendorContactUpdatedPayload(_APPayloadBase):
    vendor_id: uuid.UUID
    contact_id: uuid.UUID
    before: dict[str, Any]
    after: dict[str, Any]


class VendorContactRemovedPayload(_APPayloadBase):
    vendor_id: uuid.UUID
    contact_id: uuid.UUID


TYPE_VENDOR_CREATED = "ap.VendorCreated"
TYPE_VENDOR_UPDATED = "ap.VendorUpdated"
TYPE_VENDOR_ARCHIVED = "ap.VendorArchived"
TYPE_VENDOR_UNARCHIVED = "ap.VendorUnarchived"
TYPE_VENDOR_CONTACT_ADDED = "ap.VendorContactAdded"
TYPE_VENDOR_CONTACT_UPDATED = "ap.VendorContactUpdated"
TYPE_VENDOR_CONTACT_REMOVED = "ap.VendorContactRemoved"


register_event(TYPE_VENDOR_CREATED, VendorCreatedPayload)
register_event(TYPE_VENDOR_UPDATED, VendorUpdatedPayload)
register_event(TYPE_VENDOR_ARCHIVED, VendorArchivedPayload)
register_event(TYPE_VENDOR_UNARCHIVED, VendorUnarchivedPayload)
register_event(TYPE_VENDOR_CONTACT_ADDED, VendorContactAddedPayload)
register_event(TYPE_VENDOR_CONTACT_UPDATED, VendorContactUpdatedPayload)
register_event(TYPE_VENDOR_CONTACT_REMOVED, VendorContactRemovedPayload)
