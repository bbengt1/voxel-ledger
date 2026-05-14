"""Custom-fields service (Phase 2.5).

Manages the ``custom_field`` aggregate plus a payload-validator used by
catalog services before they persist a ``custom_fields`` jsonb dict.

Validation is schema-on-read: unknown keys are tolerated (a warning is
logged) so an old row can still be read after a key is archived. All
required active fields must be present; type checking is performed per
``field_type``. ``validate_payload`` returns a normalized dict (numbers
canonicalized via Decimal, dates parsed via ``datetime.fromisoformat``,
booleans coerced from native ``bool``).
"""

from __future__ import annotations

import logging
import re
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.events.types import custom_fields as cf_events
from app.models.custom_field import (
    CUSTOM_FIELD_ENTITY_TYPES,
    CustomField,
    CustomFieldType,
)
from app.schemas.events import EventCreate
from app.services import event_store

logger = logging.getLogger(__name__)


KEY_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


class CustomFieldsServiceError(Exception):
    """Base; routers map to 400."""


class CustomFieldNotFoundError(CustomFieldsServiceError):
    pass


class DuplicateCustomFieldError(CustomFieldsServiceError):
    pass


class InvalidCustomFieldError(CustomFieldsServiceError):
    pass


class CustomFieldValidationError(CustomFieldsServiceError):
    """Raised when ``validate_payload`` rejects a per-entity payload.

    ``detail`` is a dict mapping field key -> reason string. Routers
    re-raise as HTTP 400 with this detail as the response body.
    """

    def __init__(self, errors: dict[str, str]) -> None:
        super().__init__(f"custom-fields validation failed: {errors}")
        self.errors = errors


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _emit(
    session: AsyncSession,
    *,
    event_type: str,
    aggregate_id: uuid.UUID,
    payload: dict[str, Any],
    actor_user_id: uuid.UUID | None,
) -> None:
    await event_store.append(
        EventCreate(
            type=event_type,
            aggregate_type=cf_events.AGGREGATE_TYPE_CUSTOM_FIELD,
            aggregate_id=aggregate_id,
            payload=payload,
            occurred_at=datetime.now(UTC),
            correlation_id=uuid.uuid4(),
            actor_user_id=actor_user_id,
        ),
        session=session,
    )


def _check_entity_type(entity_type: str) -> None:
    if entity_type not in CUSTOM_FIELD_ENTITY_TYPES:
        raise InvalidCustomFieldError(
            f"entity_type {entity_type!r} is not one of {CUSTOM_FIELD_ENTITY_TYPES}"
        )


def _check_key(key: str) -> None:
    if not KEY_PATTERN.match(key):
        raise InvalidCustomFieldError(
            f"key {key!r} must match snake_case pattern {KEY_PATTERN.pattern}"
        )


def _check_field_type_options(
    field_type: CustomFieldType, options: list[dict[str, Any]] | None
) -> None:
    if field_type is CustomFieldType.SELECT:
        if not options:
            raise InvalidCustomFieldError("field_type 'select' requires a non-empty options list")
        for opt in options:
            if not isinstance(opt, dict) or "value" not in opt or "label" not in opt:
                raise InvalidCustomFieldError("each option must be a dict with 'value' and 'label'")
    elif options:
        raise InvalidCustomFieldError(f"field_type {field_type.value!r} must not carry options")


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


async def _find_active_duplicate(
    session: AsyncSession,
    *,
    entity_type: str,
    key: str,
    exclude_id: uuid.UUID | None = None,
) -> uuid.UUID | None:
    stmt = (
        select(CustomField.id)
        .where(CustomField.entity_type == entity_type)
        .where(CustomField.key == key)
        .where(CustomField.is_archived.is_(False))
    )
    if exclude_id is not None:
        stmt = stmt.where(CustomField.id != exclude_id)
    return (await session.execute(stmt)).scalar_one_or_none()


async def create(
    session: AsyncSession,
    *,
    entity_type: str,
    key: str,
    label: str,
    field_type: CustomFieldType,
    options: list[dict[str, Any]] | None,
    required: bool,
    default_value: Any | None,
    display_order: int,
    actor_user_id: uuid.UUID | None,
) -> CustomField:
    _check_entity_type(entity_type)
    _check_key(key)
    _check_field_type_options(field_type, options)

    existing = await _find_active_duplicate(session, entity_type=entity_type, key=key)
    if existing is not None:
        raise DuplicateCustomFieldError(
            f"active custom_field with key {key!r} already exists for {entity_type!r}"
        )

    cf = CustomField(
        entity_type=entity_type,
        key=key,
        label=label.strip(),
        field_type=field_type,
        options=options,
        required=required,
        default_value=default_value,
        display_order=display_order,
        is_archived=False,
    )
    session.add(cf)
    await session.flush()

    await _emit(
        session,
        event_type=cf_events.TYPE_CUSTOM_FIELD_CREATED,
        aggregate_id=cf.id,
        payload={
            "custom_field_id": str(cf.id),
            "entity_type": cf.entity_type,
            "key": cf.key,
            "label": cf.label,
            "field_type": cf.field_type.value,
            "required": cf.required,
        },
        actor_user_id=actor_user_id,
    )
    return cf


async def get(session: AsyncSession, custom_field_id: uuid.UUID) -> CustomField:
    stmt = select(CustomField).where(CustomField.id == custom_field_id)
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise CustomFieldNotFoundError(str(custom_field_id))
    return row


_EDITABLE_FIELDS = (
    "label",
    "options",
    "required",
    "default_value",
    "display_order",
)


async def update(
    session: AsyncSession,
    *,
    custom_field_id: uuid.UUID,
    patch: dict[str, Any],
    actor_user_id: uuid.UUID | None,
) -> CustomField:
    target = await get(session, custom_field_id)

    before: dict[str, Any] = {}
    after: dict[str, Any] = {}
    for field in _EDITABLE_FIELDS:
        if field not in patch:
            continue
        new_value = patch[field]
        if isinstance(new_value, str):
            new_value = new_value.strip()
        current = getattr(target, field)
        if current == new_value:
            continue
        before[field] = current
        after[field] = new_value
        setattr(target, field, new_value)

    if "options" in after or "field_type" in after:
        _check_field_type_options(target.field_type, target.options)

    if not before:
        return target

    await session.flush()

    await _emit(
        session,
        event_type=cf_events.TYPE_CUSTOM_FIELD_UPDATED,
        aggregate_id=target.id,
        payload={
            "custom_field_id": str(target.id),
            "before": before,
            "after": after,
        },
        actor_user_id=actor_user_id,
    )
    return target


async def archive(
    session: AsyncSession,
    *,
    custom_field_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
) -> CustomField:
    target = await get(session, custom_field_id)
    if target.is_archived:
        return target
    target.is_archived = True
    await session.flush()
    await _emit(
        session,
        event_type=cf_events.TYPE_CUSTOM_FIELD_ARCHIVED,
        aggregate_id=target.id,
        payload={"custom_field_id": str(target.id)},
        actor_user_id=actor_user_id,
    )
    return target


async def unarchive(
    session: AsyncSession,
    *,
    custom_field_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
) -> CustomField:
    target = await get(session, custom_field_id)
    if not target.is_archived:
        return target
    existing = await _find_active_duplicate(
        session,
        entity_type=target.entity_type,
        key=target.key,
        exclude_id=target.id,
    )
    if existing is not None:
        raise DuplicateCustomFieldError(
            f"cannot unarchive: an active field with key {target.key!r} already exists"
        )
    target.is_archived = False
    await session.flush()
    await _emit(
        session,
        event_type=cf_events.TYPE_CUSTOM_FIELD_UNARCHIVED,
        aggregate_id=target.id,
        payload={"custom_field_id": str(target.id)},
        actor_user_id=actor_user_id,
    )
    return target


async def list_for_entity(
    session: AsyncSession,
    *,
    entity_type: str,
    include_archived: bool = False,
) -> list[CustomField]:
    _check_entity_type(entity_type)
    stmt = select(CustomField).where(CustomField.entity_type == entity_type)
    if not include_archived:
        stmt = stmt.where(CustomField.is_archived.is_(False))
    stmt = stmt.order_by(CustomField.display_order, CustomField.created_at)
    return list((await session.execute(stmt)).scalars().all())


# ---------------------------------------------------------------------------
# Payload validation (the schema-on-read path)
# ---------------------------------------------------------------------------


def _validate_one(field: CustomField, raw: Any) -> tuple[Any, str | None]:
    ft = field.field_type
    if ft is CustomFieldType.STRING:
        if not isinstance(raw, str):
            return None, "expected string"
        return raw, None
    if ft is CustomFieldType.NUMBER:
        try:
            return Decimal(str(raw)), None
        except (InvalidOperation, ValueError, TypeError):
            return None, "expected number"
    if ft is CustomFieldType.BOOLEAN:
        if not isinstance(raw, bool):
            return None, "expected boolean"
        return raw, None
    if ft is CustomFieldType.DATE:
        if isinstance(raw, datetime):
            return raw, None
        if isinstance(raw, date):
            return raw, None
        if not isinstance(raw, str):
            return None, "expected ISO 8601 date or datetime string"
        try:
            return datetime.fromisoformat(raw), None
        except ValueError:
            return None, "invalid ISO 8601 date or datetime"
    if ft is CustomFieldType.SELECT:
        if field.options is None:
            return None, "select field has no options configured"
        if not isinstance(raw, str):
            return None, "expected string matching one option value"
        allowed = {opt["value"] for opt in field.options if isinstance(opt, dict)}
        if raw not in allowed:
            return None, f"value not in allowed options: {sorted(allowed)}"
        return raw, None
    return None, f"unsupported field_type {ft!r}"


def _canonicalize(value: Any) -> Any:
    """Return a JSON-serializable canonical form for storage."""
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return value


async def validate_payload(
    entity_type: str,
    payload: dict[str, Any] | None,
    *,
    session: AsyncSession,
) -> dict[str, Any]:
    """Validate and normalize a ``custom_fields`` payload.

    Loads active field definitions for ``entity_type``. All required
    fields must be present; type validators run per field_type. Unknown
    keys are tolerated (schema-on-read) but a warning is logged per
    unknown key. Returns the canonicalized payload ready for JSON
    persistence.

    Raises ``CustomFieldValidationError`` mapped to HTTP 400.
    """
    _check_entity_type(entity_type)
    payload = dict(payload or {})

    active = await list_for_entity(session, entity_type=entity_type)
    by_key = {cf.key: cf for cf in active}

    errors: dict[str, str] = {}
    normalized: dict[str, Any] = {}

    # Required-presence check.
    for cf in active:
        if cf.required and cf.key not in payload:
            errors[cf.key] = "required field missing"

    for key, raw in payload.items():
        cf = by_key.get(key)
        if cf is None:
            logger.warning(
                "custom_fields: tolerating unknown key %r on entity_type=%r",
                key,
                entity_type,
            )
            # Keep the unknown key as-is (schema-on-read survives definition removal).
            normalized[key] = raw
            continue
        if raw is None:
            if cf.required:
                errors[key] = "required field cannot be null"
            else:
                normalized[key] = None
            continue
        validated, err = _validate_one(cf, raw)
        if err is not None:
            errors[key] = err
            continue
        normalized[key] = _canonicalize(validated)

    if errors:
        raise CustomFieldValidationError(errors)

    return normalized


__all__ = [
    "CustomFieldNotFoundError",
    "CustomFieldValidationError",
    "CustomFieldsServiceError",
    "DuplicateCustomFieldError",
    "InvalidCustomFieldError",
    "archive",
    "create",
    "get",
    "list_for_entity",
    "unarchive",
    "update",
    "validate_payload",
]
