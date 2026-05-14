"""Operational settings service (Phase 1.5).

Runtime-editable, typed key/value settings (cost-engine inputs, POS
padding, reference-prefix widths, ...). Distinct from
``app.core.settings.Settings``, which is the deployment-time env-driven
configuration loaded once at boot.

The schema registry in ``schemas`` is the single source of truth for which
keys exist, their types, and their defaults. ``service.SettingsService``
is the read/write surface; routers and other services should only call
through it (never query the ``setting`` table directly).
"""

from app.services.settings import schemas  # noqa: F401  (registers schemas)
from app.services.settings.cache import SettingsCache, get_cache
from app.services.settings.schemas import (
    SettingSchema,
    UnknownSettingError,
    all_schemas,
    get_schema,
    register,
)
from app.services.settings.service import SettingsService, validate_stored_settings

__all__ = [
    "SettingSchema",
    "SettingsCache",
    "SettingsService",
    "UnknownSettingError",
    "all_schemas",
    "get_cache",
    "get_schema",
    "register",
    "validate_stored_settings",
]
