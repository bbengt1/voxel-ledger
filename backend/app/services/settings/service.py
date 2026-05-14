"""SettingsService — read/write surface for operational settings.

All access to the ``setting`` table flows through here. Routers and other
services must NOT query the table directly: they would bypass cache, the
schema registry's type validation, and the ``settings.SettingChanged``
event emission.

Transactional contract
----------------------
``set`` and ``set_many`` upsert the row(s) and append the corresponding
``settings.SettingChanged`` event in the *same* session the caller passes
in. The caller owns the transaction — we never commit. Bulk update is
atomic because every row write and every event append happens before
control returns; if any value fails validation, nothing has been touched.

Decimal handling
----------------
Decimals are persisted as canonical strings inside the JSON column so the
SQLite + Postgres + JSON-codec sandwich doesn't quietly coerce them to
floats. ``_serialize_for_storage`` and ``_deserialize_from_storage``
round-trip via the schema; once a value comes out, it's a real Decimal
again.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.events.types.settings import TYPE_SETTING_CHANGED
from app.models.setting import Setting
from app.schemas.events import EventCreate
from app.services import event_store
from app.services.settings.cache import get_cache
from app.services.settings.schemas import (
    SettingSchema,
    UnknownSettingError,
    all_schemas,
    get_schema,
)

log = logging.getLogger(__name__)

# A stable UUID namespace for hashing setting keys into aggregate_ids. The
# event log requires a UUID aggregate_id; we want the same key to map to
# the same aggregate every time so a downstream consumer can group history
# by setting without an extra lookup table.
_SETTING_NAMESPACE = uuid.UUID("d5e7f1c2-1f60-4f00-8b3c-5e7d1a9c2a10")


def key_to_aggregate_id(key: str) -> uuid.UUID:
    """Deterministic UUID5 for ``key``. Same input → same UUID forever."""
    return uuid.uuid5(_SETTING_NAMESPACE, key)


class SettingValidationError(ValueError):
    """A write value failed validation against its schema."""


@dataclass
class SettingRecord:
    """Hydrated setting, merged with its schema default.

    ``value`` is always populated (default if no row); ``updated_at`` /
    ``updated_by_user_id`` are ``None`` when the value came from the
    default.
    """

    key: str
    value: Any
    default: Any
    schema_type: str
    updated_at: datetime | None
    updated_by_user_id: uuid.UUID | None


# ---------------------------------------------------------------------------
# (De)serialization helpers.
# ---------------------------------------------------------------------------


def _serialize_for_storage(value: Any) -> Any:
    """Convert a validated value to its JSON-storable form.

    - Decimals → canonical string (so SQLite's JSON codec doesn't float them).
    - dicts / lists → recursed.
    - Everything else → passed through (Pydantic already enforced the type).
    """
    if isinstance(value, Decimal):
        # ``str(Decimal)`` keeps trailing zeros and precision, which is
        # what we want for monetary canonicalization.
        return str(value)
    if isinstance(value, dict):
        return {k: _serialize_for_storage(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_serialize_for_storage(v) for v in value]
    return value


def _serialize_for_event(value: Any) -> Any:
    """Same as ``_serialize_for_storage`` — the event payload needs the
    same JSON-safe shape, and Pydantic's ``model_dump(mode='json')`` on
    the SettingChangedPayload model will pass our pre-serialized values
    through untouched."""
    return _serialize_for_storage(value)


def _deserialize_from_storage(schema_cls: type[SettingSchema], stored: Any) -> Any:
    """Inverse of ``_serialize_for_storage``.

    Round-trips through the schema so the returned value has the right
    Python type (Decimal, dict[str, int], etc.).
    """
    # The schema's `value` field type is the storage type. Pydantic will
    # coerce string -> Decimal during validation, which is exactly the
    # behavior we want here.
    validated = schema_cls(value=stored)
    return validated.value


def _schema_type_name(schema_cls: type[SettingSchema]) -> str:
    """Friendly type string for API responses (``Decimal``, ``str``,
    ``dict[str, int]``...)."""
    field = schema_cls.model_fields["value"]
    annotation = field.annotation
    return getattr(annotation, "__name__", str(annotation))


# ---------------------------------------------------------------------------
# Service.
# ---------------------------------------------------------------------------


class SettingsService:
    """Read/write operational settings.

    Static methods on a class purely so callers can ``from app.services
    import settings as svc; await svc.SettingsService.get(...)`` without
    instantiating bookkeeping state.
    """

    @staticmethod
    async def get(key: str, *, session: AsyncSession) -> Any:
        """Return the typed value for ``key``.

        Falls back to the schema default if no row exists. Raises
        :class:`UnknownSettingError` for unregistered keys.
        """
        schema_cls = get_schema(key)
        cache = get_cache()
        cached = cache.get(key)
        if cached is not None:
            return cached

        stmt = select(Setting).where(Setting.key == key)
        row = (await session.execute(stmt)).scalar_one_or_none()
        if row is None:
            value: Any = schema_cls.default
        else:
            value = _deserialize_from_storage(schema_cls, row.value)
        cache.set(key, value)
        return value

    @staticmethod
    async def get_record(key: str, *, session: AsyncSession) -> SettingRecord:
        """Return the full record (value + provenance + schema metadata)."""
        schema_cls = get_schema(key)
        stmt = select(Setting).where(Setting.key == key)
        row = (await session.execute(stmt)).scalar_one_or_none()
        if row is None:
            value: Any = schema_cls.default
            updated_at: datetime | None = None
            updated_by: uuid.UUID | None = None
        else:
            value = _deserialize_from_storage(schema_cls, row.value)
            updated_at = row.updated_at
            updated_by = row.updated_by_user_id
        return SettingRecord(
            key=key,
            value=value,
            default=schema_cls.default,
            schema_type=_schema_type_name(schema_cls),
            updated_at=updated_at,
            updated_by_user_id=updated_by,
        )

    @staticmethod
    async def list_all(*, session: AsyncSession) -> list[SettingRecord]:
        """Return every registered setting merged with its stored value.

        Sorted by key. Schemas without a stored row return the default
        with ``updated_at=None``.
        """
        rows_by_key: dict[str, Setting] = {}
        stmt = select(Setting)
        for row in (await session.execute(stmt)).scalars().all():
            rows_by_key[row.key] = row

        out: list[SettingRecord] = []
        for key, schema_cls in all_schemas().items():
            row = rows_by_key.get(key)
            if row is None:
                value: Any = schema_cls.default
                updated_at: datetime | None = None
                updated_by: uuid.UUID | None = None
            else:
                value = _deserialize_from_storage(schema_cls, row.value)
                updated_at = row.updated_at
                updated_by = row.updated_by_user_id
            out.append(
                SettingRecord(
                    key=key,
                    value=value,
                    default=schema_cls.default,
                    schema_type=_schema_type_name(schema_cls),
                    updated_at=updated_at,
                    updated_by_user_id=updated_by,
                )
            )
        return out

    @staticmethod
    async def set(
        key: str,
        value: Any,
        *,
        session: AsyncSession,
        actor_user_id: uuid.UUID | None,
    ) -> Any:
        """Validate and persist ``value`` for ``key``, emitting an event.

        Returns the validated (typed) value. The caller is responsible for
        committing the surrounding transaction; on rollback both the row
        upsert and the event are discarded.
        """
        schema_cls = get_schema(key)
        try:
            validated = schema_cls(value=value).value
        except ValidationError as exc:
            raise SettingValidationError(str(exc)) from exc

        # Snapshot the old value (default if no row) for the event payload.
        # We avoid the cache here so the event's old_value reflects the
        # durable state, not a possibly-stale in-memory copy.
        stmt = select(Setting).where(Setting.key == key)
        existing = (await session.execute(stmt)).scalar_one_or_none()
        if existing is None:
            old_value: Any = schema_cls.default
        else:
            old_value = _deserialize_from_storage(schema_cls, existing.value)

        stored = _serialize_for_storage(validated)
        if existing is None:
            session.add(Setting(key=key, value=stored, updated_by_user_id=actor_user_id))
        else:
            existing.value = stored
            existing.updated_by_user_id = actor_user_id
            # SQLAlchemy's ``onupdate=func.now()`` will fire on flush.
        await session.flush()

        # Append the event INSIDE the same transaction. The cache-busting
        # projection runs synchronously from ``event_store.append`` and
        # invalidates the cache before this call returns — so the next
        # read sees the new value within the same tick.
        await event_store.append(
            EventCreate(
                type=TYPE_SETTING_CHANGED,
                aggregate_type="Setting",
                aggregate_id=key_to_aggregate_id(key),
                payload={
                    "key": key,
                    "old_value": _serialize_for_event(old_value),
                    "new_value": _serialize_for_event(validated),
                },
                occurred_at=datetime.now(UTC),
                correlation_id=uuid.uuid4(),
                actor_user_id=actor_user_id,
            ),
            session=session,
        )

        # Belt-and-braces: also bust the cache locally. The projection
        # already did this, but if the cache module is ever rebound or
        # the projection registry is reset mid-test, we still want a
        # fresh read on the next call.
        get_cache().invalidate(key)
        return validated

    @staticmethod
    async def set_many(
        updates: dict[str, Any],
        *,
        session: AsyncSession,
        actor_user_id: uuid.UUID | None,
    ) -> dict[str, Any]:
        """Atomic batch update.

        Validates every value first (so an invalid entry rolls everything
        back before any writes happen), then applies each ``set`` in
        order. The caller commits.

        Returns a dict of key → validated value for the keys that changed.
        """
        # 1. Validate everything up-front. Unknown key → UnknownSettingError;
        #    bad value → SettingValidationError. Neither has written
        #    anything yet, so the caller can just re-raise and roll back.
        validated_pairs: list[tuple[str, Any]] = []
        for key, raw in updates.items():
            schema_cls = get_schema(key)
            try:
                validated = schema_cls(value=raw).value
            except ValidationError as exc:
                raise SettingValidationError(f"setting {key!r}: {exc}") from exc
            validated_pairs.append((key, validated))

        # 2. Apply. Each ``set`` emits its own event and busts cache. If
        #    any individual write trips an integrity error, the session
        #    is already poisoned and the caller will roll back.
        out: dict[str, Any] = {}
        for key, validated in validated_pairs:
            applied = await SettingsService.set(
                key,
                validated,
                session=session,
                actor_user_id=actor_user_id,
            )
            out[key] = applied
        return out


# ---------------------------------------------------------------------------
# Startup validation.
# ---------------------------------------------------------------------------


async def validate_stored_settings(*, session: AsyncSession) -> list[str]:
    """Walk the ``setting`` table on boot and log warnings for bad rows.

    Returns the list of keys that failed validation (useful for tests).
    Never raises — the schema default still wins at read time, so a bad
    stored row degrades gracefully rather than crashing the app.
    """
    bad_keys: list[str] = []
    rows = (await session.execute(select(Setting))).scalars().all()
    for row in rows:
        try:
            schema_cls = get_schema(row.key)
        except UnknownSettingError:
            log.warning(
                "settings.startup.unknown_key",
                extra={"key": row.key},
            )
            bad_keys.append(row.key)
            continue
        try:
            schema_cls(value=row.value)
        except ValidationError as exc:
            log.warning(
                "settings.startup.invalid_value",
                extra={"key": row.key, "errors": str(exc)},
            )
            bad_keys.append(row.key)
    return bad_keys
