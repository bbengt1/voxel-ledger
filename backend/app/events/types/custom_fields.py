"""Platform: custom-fields & form-templates event types (Phase 2.5).

Both aggregates live in the platform bounded context. ``CustomField``
events use ``aggregate_type == "custom_field"``; form templates use
``"form_template"``. Payloads carry the IDs and only the metadata that
matters for audit display + replay (``entity_type``, ``key``, ``label``,
``field_type``, ``required``, ``name``). Sensitive content cannot appear
here — there's none to begin with.
"""

from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.events.registry import register_event

AGGREGATE_TYPE_CUSTOM_FIELD: str = "custom_field"
AGGREGATE_TYPE_FORM_TEMPLATE: str = "form_template"


class _PayloadBase(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --- Custom field events --------------------------------------------------


class CustomFieldCreatedPayload(_PayloadBase):
    custom_field_id: uuid.UUID
    entity_type: str
    key: str
    label: str
    field_type: str
    required: bool


class CustomFieldUpdatedPayload(_PayloadBase):
    custom_field_id: uuid.UUID
    before: dict[str, Any]
    after: dict[str, Any]


class CustomFieldArchivedPayload(_PayloadBase):
    custom_field_id: uuid.UUID


class CustomFieldUnarchivedPayload(_PayloadBase):
    custom_field_id: uuid.UUID


TYPE_CUSTOM_FIELD_CREATED = "platform.CustomFieldCreated"
TYPE_CUSTOM_FIELD_UPDATED = "platform.CustomFieldUpdated"
TYPE_CUSTOM_FIELD_ARCHIVED = "platform.CustomFieldArchived"
TYPE_CUSTOM_FIELD_UNARCHIVED = "platform.CustomFieldUnarchived"


register_event(TYPE_CUSTOM_FIELD_CREATED, CustomFieldCreatedPayload)
register_event(TYPE_CUSTOM_FIELD_UPDATED, CustomFieldUpdatedPayload)
register_event(TYPE_CUSTOM_FIELD_ARCHIVED, CustomFieldArchivedPayload)
register_event(TYPE_CUSTOM_FIELD_UNARCHIVED, CustomFieldUnarchivedPayload)


# --- Form template events -------------------------------------------------


class FormTemplateCreatedPayload(_PayloadBase):
    template_id: uuid.UUID
    entity_type: str
    name: str
    is_default_for_entity_type: bool


class FormTemplateUpdatedPayload(_PayloadBase):
    template_id: uuid.UUID
    before: dict[str, Any]
    after: dict[str, Any]


class FormTemplateDefaultedPayload(_PayloadBase):
    template_id: uuid.UUID
    entity_type: str
    previous_default_template_id: uuid.UUID | None = None


class FormTemplateArchivedPayload(_PayloadBase):
    template_id: uuid.UUID


class FormTemplateFieldAddedPayload(_PayloadBase):
    template_id: uuid.UUID
    custom_field_id: uuid.UUID
    display_order: int


class FormTemplateFieldRemovedPayload(_PayloadBase):
    template_id: uuid.UUID
    custom_field_id: uuid.UUID


TYPE_FORM_TEMPLATE_CREATED = "platform.FormTemplateCreated"
TYPE_FORM_TEMPLATE_UPDATED = "platform.FormTemplateUpdated"
TYPE_FORM_TEMPLATE_DEFAULTED = "platform.FormTemplateDefaulted"
TYPE_FORM_TEMPLATE_ARCHIVED = "platform.FormTemplateArchived"
TYPE_FORM_TEMPLATE_FIELD_ADDED = "platform.FormTemplateFieldAdded"
TYPE_FORM_TEMPLATE_FIELD_REMOVED = "platform.FormTemplateFieldRemoved"


register_event(TYPE_FORM_TEMPLATE_CREATED, FormTemplateCreatedPayload)
register_event(TYPE_FORM_TEMPLATE_UPDATED, FormTemplateUpdatedPayload)
register_event(TYPE_FORM_TEMPLATE_DEFAULTED, FormTemplateDefaultedPayload)
register_event(TYPE_FORM_TEMPLATE_ARCHIVED, FormTemplateArchivedPayload)
register_event(TYPE_FORM_TEMPLATE_FIELD_ADDED, FormTemplateFieldAddedPayload)
register_event(TYPE_FORM_TEMPLATE_FIELD_REMOVED, FormTemplateFieldRemovedPayload)
