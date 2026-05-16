"""AR-bounded-context event types (Phase 7.1, #109).

Aggregates landing here:

* ``customer`` (Phase 7.1) — the AR-side subject identity. Created /
  updated / archived / unarchived events, plus the nested contact CRUD.

CRITICAL PII RULE
-----------------
``primary_email``, ``phone``, ``billing_address``, ``shipping_address``,
and ``notes`` MUST NEVER be whitelisted into the audit excerpt. The
payload carries them so the event log can reconstruct the customer, but
the audit denormalization keeps strictly to ``customer_number`` and
``display_name``. See ``app/projections/audit/excerpts.py``.
"""

from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.events.registry import register_event

AGGREGATE_TYPE_CUSTOMER: str = "customer"


class _ARPayloadBase(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --- Customers --------------------------------------------------------------


class CustomerCreatedPayload(_ARPayloadBase):
    customer_id: uuid.UUID
    customer_number: str
    display_name: str
    legal_name: str | None = None
    primary_email: str | None = None
    phone: str | None = None
    payment_terms_days: int
    default_revenue_account_id: uuid.UUID | None = None
    default_ar_account_id: uuid.UUID | None = None
    tax_profile_id: uuid.UUID | None = None
    state: str


class CustomerUpdatedPayload(_ARPayloadBase):
    customer_id: uuid.UUID
    before: dict[str, Any]
    after: dict[str, Any]


class CustomerArchivedPayload(_ARPayloadBase):
    customer_id: uuid.UUID


class CustomerUnarchivedPayload(_ARPayloadBase):
    customer_id: uuid.UUID


class CustomerContactAddedPayload(_ARPayloadBase):
    customer_id: uuid.UUID
    contact_id: uuid.UUID
    name: str
    role_label: str | None = None
    is_primary: bool


class CustomerContactUpdatedPayload(_ARPayloadBase):
    customer_id: uuid.UUID
    contact_id: uuid.UUID
    before: dict[str, Any]
    after: dict[str, Any]


class CustomerContactRemovedPayload(_ARPayloadBase):
    customer_id: uuid.UUID
    contact_id: uuid.UUID


TYPE_CUSTOMER_CREATED = "ar.CustomerCreated"
TYPE_CUSTOMER_UPDATED = "ar.CustomerUpdated"
TYPE_CUSTOMER_ARCHIVED = "ar.CustomerArchived"
TYPE_CUSTOMER_UNARCHIVED = "ar.CustomerUnarchived"
TYPE_CUSTOMER_CONTACT_ADDED = "ar.CustomerContactAdded"
TYPE_CUSTOMER_CONTACT_UPDATED = "ar.CustomerContactUpdated"
TYPE_CUSTOMER_CONTACT_REMOVED = "ar.CustomerContactRemoved"


register_event(TYPE_CUSTOMER_CREATED, CustomerCreatedPayload)
register_event(TYPE_CUSTOMER_UPDATED, CustomerUpdatedPayload)
register_event(TYPE_CUSTOMER_ARCHIVED, CustomerArchivedPayload)
register_event(TYPE_CUSTOMER_UNARCHIVED, CustomerUnarchivedPayload)
register_event(TYPE_CUSTOMER_CONTACT_ADDED, CustomerContactAddedPayload)
register_event(TYPE_CUSTOMER_CONTACT_UPDATED, CustomerContactUpdatedPayload)
register_event(TYPE_CUSTOMER_CONTACT_REMOVED, CustomerContactRemovedPayload)
