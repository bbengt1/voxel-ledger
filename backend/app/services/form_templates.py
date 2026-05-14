"""Form-templates service (Phase 2.5).

CRUD for ``form_template`` rows plus the ``set_default`` atomic flip
(mirrors the rates ``set_default`` from #38). ``form_template_field``
join rows are managed by ``add_field`` / ``remove_field``. The resolved
helper composes the template metadata with the ordered list of active
field definitions for read-side consumption.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.events.types import custom_fields as cf_events
from app.models.custom_field import (
    CUSTOM_FIELD_ENTITY_TYPES,
    CustomField,
    FormTemplate,
    FormTemplateField,
)
from app.schemas.events import EventCreate
from app.services import event_store
from app.services.custom_fields import (
    CustomFieldNotFoundError,
    InvalidCustomFieldError,
)


class FormTemplatesServiceError(Exception):
    """Base; routers map to 400."""


class FormTemplateNotFoundError(FormTemplatesServiceError):
    pass


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
            aggregate_type=cf_events.AGGREGATE_TYPE_FORM_TEMPLATE,
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


async def _current_default(
    session: AsyncSession,
    entity_type: str,
    *,
    exclude_id: uuid.UUID | None = None,
) -> FormTemplate | None:
    stmt = (
        select(FormTemplate)
        .where(FormTemplate.entity_type == entity_type)
        .where(FormTemplate.is_default_for_entity_type.is_(True))
    )
    if exclude_id is not None:
        stmt = stmt.where(FormTemplate.id != exclude_id)
    return (await session.execute(stmt)).scalar_one_or_none()


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


async def create(
    session: AsyncSession,
    *,
    entity_type: str,
    name: str,
    description: str | None,
    is_default_for_entity_type: bool,
    display_order: int,
    actor_user_id: uuid.UUID | None,
) -> FormTemplate:
    _check_entity_type(entity_type)

    previous_default: FormTemplate | None = None
    if is_default_for_entity_type:
        previous_default = await _current_default(session, entity_type)
        if previous_default is not None:
            previous_default.is_default_for_entity_type = False
            await session.flush()

    tmpl = FormTemplate(
        entity_type=entity_type,
        name=name.strip(),
        description=description.strip() if description else None,
        is_default_for_entity_type=is_default_for_entity_type,
        display_order=display_order,
        is_archived=False,
    )
    session.add(tmpl)
    await session.flush()

    await _emit(
        session,
        event_type=cf_events.TYPE_FORM_TEMPLATE_CREATED,
        aggregate_id=tmpl.id,
        payload={
            "template_id": str(tmpl.id),
            "entity_type": tmpl.entity_type,
            "name": tmpl.name,
            "is_default_for_entity_type": tmpl.is_default_for_entity_type,
        },
        actor_user_id=actor_user_id,
    )
    if is_default_for_entity_type:
        await _emit(
            session,
            event_type=cf_events.TYPE_FORM_TEMPLATE_DEFAULTED,
            aggregate_id=tmpl.id,
            payload={
                "template_id": str(tmpl.id),
                "entity_type": tmpl.entity_type,
                "previous_default_template_id": (
                    str(previous_default.id) if previous_default is not None else None
                ),
            },
            actor_user_id=actor_user_id,
        )
    return tmpl


async def get(session: AsyncSession, template_id: uuid.UUID) -> FormTemplate:
    stmt = select(FormTemplate).where(FormTemplate.id == template_id)
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise FormTemplateNotFoundError(str(template_id))
    return row


_EDITABLE_FIELDS = ("name", "description", "display_order")


async def update(
    session: AsyncSession,
    *,
    template_id: uuid.UUID,
    patch: dict[str, Any],
    actor_user_id: uuid.UUID | None,
) -> FormTemplate:
    target = await get(session, template_id)

    before: dict[str, Any] = {}
    after: dict[str, Any] = {}
    for field in _EDITABLE_FIELDS:
        if field not in patch:
            continue
        new_value = patch[field]
        if isinstance(new_value, str):
            stripped = new_value.strip()
            new_value = None if field == "description" and stripped == "" else stripped
        current = getattr(target, field)
        if current == new_value:
            continue
        before[field] = current
        after[field] = new_value
        setattr(target, field, new_value)

    if not before:
        return target

    await session.flush()
    await _emit(
        session,
        event_type=cf_events.TYPE_FORM_TEMPLATE_UPDATED,
        aggregate_id=target.id,
        payload={
            "template_id": str(target.id),
            "before": before,
            "after": after,
        },
        actor_user_id=actor_user_id,
    )
    return target


async def set_default(
    session: AsyncSession,
    *,
    template_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
) -> FormTemplate:
    target = await get(session, template_id)
    if target.is_archived:
        raise FormTemplatesServiceError("cannot set an archived template as default")
    previous_default = await _current_default(session, target.entity_type, exclude_id=target.id)
    if previous_default is not None:
        previous_default.is_default_for_entity_type = False
        await session.flush()
    if not target.is_default_for_entity_type:
        target.is_default_for_entity_type = True
        await session.flush()
    await _emit(
        session,
        event_type=cf_events.TYPE_FORM_TEMPLATE_DEFAULTED,
        aggregate_id=target.id,
        payload={
            "template_id": str(target.id),
            "entity_type": target.entity_type,
            "previous_default_template_id": (
                str(previous_default.id) if previous_default is not None else None
            ),
        },
        actor_user_id=actor_user_id,
    )
    return target


async def archive(
    session: AsyncSession,
    *,
    template_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
) -> FormTemplate:
    target = await get(session, template_id)
    if target.is_archived:
        return target
    target.is_archived = True
    target.is_default_for_entity_type = False
    await session.flush()
    await _emit(
        session,
        event_type=cf_events.TYPE_FORM_TEMPLATE_ARCHIVED,
        aggregate_id=target.id,
        payload={"template_id": str(target.id)},
        actor_user_id=actor_user_id,
    )
    return target


async def list_templates(
    session: AsyncSession,
    *,
    entity_type: str | None = None,
    default_only: bool = False,
    include_archived: bool = False,
) -> list[FormTemplate]:
    stmt = select(FormTemplate)
    if entity_type is not None:
        _check_entity_type(entity_type)
        stmt = stmt.where(FormTemplate.entity_type == entity_type)
    if default_only:
        stmt = stmt.where(FormTemplate.is_default_for_entity_type.is_(True))
    if not include_archived:
        stmt = stmt.where(FormTemplate.is_archived.is_(False))
    stmt = stmt.order_by(
        FormTemplate.entity_type,
        FormTemplate.display_order,
        FormTemplate.created_at,
    )
    return list((await session.execute(stmt)).scalars().all())


# ---------------------------------------------------------------------------
# Field join management
# ---------------------------------------------------------------------------


async def add_field(
    session: AsyncSession,
    *,
    template_id: uuid.UUID,
    custom_field_id: uuid.UUID,
    display_order: int,
    actor_user_id: uuid.UUID | None,
) -> FormTemplateField:
    tmpl = await get(session, template_id)
    # Ensure the field exists and belongs to the same entity_type.
    cf_row = (
        await session.execute(select(CustomField).where(CustomField.id == custom_field_id))
    ).scalar_one_or_none()
    if cf_row is None:
        raise CustomFieldNotFoundError(str(custom_field_id))
    if cf_row.entity_type != tmpl.entity_type:
        raise FormTemplatesServiceError(
            f"custom_field entity_type {cf_row.entity_type!r} does not match "
            f"template entity_type {tmpl.entity_type!r}"
        )

    # Upsert via existing-row check (composite PK).
    existing = (
        await session.execute(
            select(FormTemplateField)
            .where(FormTemplateField.template_id == template_id)
            .where(FormTemplateField.custom_field_id == custom_field_id)
        )
    ).scalar_one_or_none()
    if existing is not None:
        existing.display_order = display_order
        await session.flush()
        join = existing
    else:
        join = FormTemplateField(
            template_id=template_id,
            custom_field_id=custom_field_id,
            display_order=display_order,
        )
        session.add(join)
        await session.flush()

    await _emit(
        session,
        event_type=cf_events.TYPE_FORM_TEMPLATE_FIELD_ADDED,
        aggregate_id=template_id,
        payload={
            "template_id": str(template_id),
            "custom_field_id": str(custom_field_id),
            "display_order": display_order,
        },
        actor_user_id=actor_user_id,
    )
    return join


async def remove_field(
    session: AsyncSession,
    *,
    template_id: uuid.UUID,
    custom_field_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
) -> None:
    existing = (
        await session.execute(
            select(FormTemplateField)
            .where(FormTemplateField.template_id == template_id)
            .where(FormTemplateField.custom_field_id == custom_field_id)
        )
    ).scalar_one_or_none()
    if existing is None:
        raise FormTemplatesServiceError("field is not attached to this template")
    await session.delete(existing)
    await session.flush()

    await _emit(
        session,
        event_type=cf_events.TYPE_FORM_TEMPLATE_FIELD_REMOVED,
        aggregate_id=template_id,
        payload={
            "template_id": str(template_id),
            "custom_field_id": str(custom_field_id),
        },
        actor_user_id=actor_user_id,
    )


# ---------------------------------------------------------------------------
# Read-side resolution
# ---------------------------------------------------------------------------


@dataclass
class ResolvedTemplate:
    template: FormTemplate
    fields: list[CustomField]


async def get_resolved(
    session: AsyncSession,
    *,
    template_id: uuid.UUID | None = None,
    entity_type: str | None = None,
) -> ResolvedTemplate:
    """Resolve a template + its ordered fields.

    Pass ``template_id`` to look up a specific template, OR
    ``entity_type`` to fetch the default for that entity. If both are
    None, raises ``FormTemplatesServiceError``.
    """
    if template_id is None and entity_type is None:
        raise FormTemplatesServiceError("must provide template_id or entity_type")

    if template_id is not None:
        tmpl = await get(session, template_id)
    else:
        assert entity_type is not None
        _check_entity_type(entity_type)
        tmpl_row = await _current_default(session, entity_type)
        if tmpl_row is None:
            raise FormTemplateNotFoundError(f"no default template for entity_type {entity_type!r}")
        tmpl = tmpl_row

    # Ordered join: form_template_field.display_order first, then
    # custom_field.display_order as tiebreak.
    stmt = (
        select(CustomField, FormTemplateField.display_order)
        .join(
            FormTemplateField,
            FormTemplateField.custom_field_id == CustomField.id,
        )
        .where(FormTemplateField.template_id == tmpl.id)
        .where(CustomField.is_archived.is_(False))
        .order_by(FormTemplateField.display_order, CustomField.display_order)
    )
    rows = (await session.execute(stmt)).all()
    fields = [row[0] for row in rows]
    return ResolvedTemplate(template=tmpl, fields=fields)


__all__ = [
    "FormTemplateNotFoundError",
    "FormTemplatesServiceError",
    "ResolvedTemplate",
    "add_field",
    "archive",
    "create",
    "get",
    "get_resolved",
    "list_templates",
    "remove_field",
    "set_default",
    "update",
]
