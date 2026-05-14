"""Event types for the operational settings module.

``settings.SettingChanged`` is emitted by ``SettingsService.set`` inside
the same transaction as the underlying upsert. The projection in
``app.projections.settings_cache`` consumes it to bust the in-process
cache; future audit / observability projections can subscribe to the same
event.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from app.events.registry import register_event

TYPE_SETTING_CHANGED = "settings.SettingChanged"


class SettingChangedPayload(BaseModel):
    """One settings.SettingChanged event.

    ``old_value`` and ``new_value`` are stored in their JSON-serializable
    form (Decimals as canonical strings, dicts as plain dicts) so the
    event payload round-trips through the registry's
    ``model_dump(mode='json')`` without lossy coercion.
    """

    key: str
    old_value: Any
    new_value: Any


register_event(TYPE_SETTING_CHANGED, SettingChangedPayload)
