"""Pydantic schemas for the custom-fields & form-templates API surface."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.custom_field import CustomFieldType


class CustomFieldOption(BaseModel):
    value: str = Field(min_length=1, max_length=64)
    label: str = Field(min_length=1, max_length=255)


class CustomFieldResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    entity_type: str
    key: str
    label: str
    field_type: CustomFieldType
    options: list[CustomFieldOption] | None = None
    required: bool
    default_value: Any | None = None
    display_order: int
    is_archived: bool
    created_at: datetime
    updated_at: datetime


class CustomFieldCreateRequest(BaseModel):
    entity_type: str = Field(min_length=1, max_length=32)
    key: str = Field(min_length=1, max_length=64)
    label: str = Field(min_length=1, max_length=255)
    field_type: CustomFieldType
    options: list[CustomFieldOption] | None = None
    required: bool = False
    default_value: Any | None = None
    display_order: int = 0


class CustomFieldUpdateRequest(BaseModel):
    """PATCH — fields the user wants to change.

    ``entity_type``, ``key``, and ``field_type`` are intentionally
    immutable: changing them would break stored data on existing rows.
    """

    label: str | None = Field(default=None, min_length=1, max_length=255)
    options: list[CustomFieldOption] | None = None
    required: bool | None = None
    default_value: Any | None = None
    display_order: int | None = None


class CustomFieldListResponse(BaseModel):
    items: list[CustomFieldResponse]


class FormTemplateFieldEntry(BaseModel):
    custom_field_id: uuid.UUID
    display_order: int


class FormTemplateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    entity_type: str
    name: str
    description: str | None = None
    is_default_for_entity_type: bool
    is_archived: bool
    display_order: int
    created_at: datetime
    updated_at: datetime


class FormTemplateCreateRequest(BaseModel):
    entity_type: str = Field(min_length=1, max_length=32)
    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=4096)
    is_default_for_entity_type: bool = False
    display_order: int = 0


class FormTemplateUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=4096)
    display_order: int | None = None


class FormTemplateListResponse(BaseModel):
    items: list[FormTemplateResponse]


class FormTemplateResolvedResponse(BaseModel):
    template: FormTemplateResponse
    fields: list[CustomFieldResponse]


class FormTemplateFieldAddRequest(BaseModel):
    custom_field_id: uuid.UUID
    display_order: int = 0
