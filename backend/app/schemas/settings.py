"""API-surface schemas for the operational settings module.

The wire representation of a setting is intentionally schema-on-read:
``value`` and ``default`` are typed as ``Any`` because every key in the
registry has its own payload shape (Decimal-as-string, dict[str, int],
plain string, ...). The frontend uses the ``schema_type`` hint to render
the editor.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class SettingResponse(BaseModel):
    """One setting, merged with its schema default and provenance."""

    key: str
    value: Any
    default: Any
    schema_type: str = Field(
        description=(
            "Friendly Python type name for the value (e.g. 'Decimal', "
            "'str', 'dict'). Used by the frontend to pick an editor."
        ),
    )
    updated_at: datetime | None = Field(
        default=None,
        description="When the row was last written. None if no row exists yet.",
    )
    updated_by_user_id: uuid.UUID | None = Field(
        default=None,
        description="User who last wrote the row. None if from default.",
    )


class SettingUpdateRequest(BaseModel):
    """PUT body for a single setting."""

    value: Any


class BulkSettingUpdateRequest(BaseModel):
    """POST body for a batch update.

    The request is all-or-nothing: if any value fails validation, no
    writes happen.
    """

    updates: dict[str, Any]


class BulkSettingUpdateResponse(BaseModel):
    """Response for a successful batch update.

    ``updated`` mirrors the request keys with their validated (typed)
    values as returned by the service.
    """

    updated: dict[str, Any]
