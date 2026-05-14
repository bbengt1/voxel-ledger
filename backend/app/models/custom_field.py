"""ORM models for custom-field definitions and form templates (Phase 2.5).

Custom fields are platform-level metadata that let owners define
schema-on-read extensions per entity type. ``custom_field`` rows declare
which keys appear in the JSON ``custom_fields`` column on the four
catalog entities (material, supply, rate, product). Form templates group
fields into ordered display surfaces; ``form_template`` + the
``form_template_field`` join carry that ordering.

A partial unique index ``ux_custom_field_entity_type_key_active``
guarantees one active key per entity_type at the DB layer; archived
rows can coexist with a freshly-defined replacement. A second partial
unique index ``ux_form_template_default_per_entity_type`` enforces
"at most one default template per entity type."
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
    text,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.core.db import Base

# JSONB on Postgres, plain JSON on SQLite (matches event log / settings).
JSONType = JSON().with_variant(JSONB(), "postgresql")


class CustomFieldType(enum.StrEnum):
    STRING = "string"
    NUMBER = "number"
    BOOLEAN = "boolean"
    DATE = "date"
    SELECT = "select"


CUSTOM_FIELD_TYPE_ENUM = SAEnum(
    CustomFieldType,
    name="custom_field_type",
    values_callable=lambda enum_cls: [member.value for member in enum_cls],
)


# Entity types the custom-fields system currently supports. Expanding
# this set is a CHECK-constraint migration, not a code change in this
# module.
CUSTOM_FIELD_ENTITY_TYPES = ("material", "supply", "rate", "product")


class CustomField(Base):
    __tablename__ = "custom_field"
    __table_args__ = (
        Index(
            "ux_custom_field_entity_type_key_active",
            "entity_type",
            "key",
            unique=True,
            sqlite_where=text("is_archived = 0"),
            postgresql_where=text("is_archived = false"),
        ),
        Index(
            "ix_custom_field_entity_type",
            "entity_type",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    entity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    key: Mapped[str] = mapped_column(String(64), nullable=False)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    field_type: Mapped[CustomFieldType] = mapped_column(CUSTOM_FIELD_TYPE_ENUM, nullable=False)

    # ``options`` is only meaningful when ``field_type == 'select'``.
    # Shape: list of {"value": str, "label": str}.
    options: Mapped[Any] = mapped_column(JSONType, nullable=True)
    required: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )
    default_value: Mapped[Any] = mapped_column(JSONType, nullable=True)
    display_order: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    is_archived: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class FormTemplate(Base):
    __tablename__ = "form_template"
    __table_args__ = (
        Index(
            "ux_form_template_default_per_entity_type",
            "entity_type",
            unique=True,
            sqlite_where=text("is_default_for_entity_type = 1"),
            postgresql_where=text("is_default_for_entity_type = true"),
        ),
        Index("ix_form_template_entity_type", "entity_type"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text(), nullable=True)
    is_default_for_entity_type: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )
    is_archived: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )
    display_order: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class FormTemplateField(Base):
    __tablename__ = "form_template_field"

    template_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("form_template.id", ondelete="CASCADE"),
        primary_key=True,
    )
    custom_field_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("custom_field.id", ondelete="CASCADE"),
        primary_key=True,
    )
    display_order: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
