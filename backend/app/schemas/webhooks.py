"""Pydantic schemas for outbound webhooks (Phase 11.1, #193)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

WebhookDeliveryStatusLiteral = Literal["pending", "delivered", "failed", "dead_letter"]


class WebhookSubscriptionCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    target_url: HttpUrl
    event_types: list[str] = Field(default_factory=list)
    is_active: bool = True


class WebhookSubscriptionUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    target_url: HttpUrl | None = None
    event_types: list[str] | None = None
    is_active: bool | None = None
    rotate_secret: bool = False


class WebhookSubscriptionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    target_url: str
    event_types: list[str]
    is_active: bool
    created_by_user_id: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime


class WebhookSubscriptionCreated(WebhookSubscriptionRead):
    """Same as :class:`WebhookSubscriptionRead` plus the one-time secret.

    Returned only on create + rotate-secret PATCH. The secret is never
    surfaced on GETs.
    """

    secret: str


class WebhookDeliveryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    subscription_id: uuid.UUID
    event_id: uuid.UUID | None = None
    event_type: str
    payload: dict[str, Any]
    attempt_count: int
    last_status: WebhookDeliveryStatusLiteral
    last_response_code: int | None = None
    last_error: str | None = None
    next_attempt_at: datetime
    created_at: datetime
    updated_at: datetime


__all__ = [
    "WebhookDeliveryRead",
    "WebhookDeliveryStatusLiteral",
    "WebhookSubscriptionCreate",
    "WebhookSubscriptionCreated",
    "WebhookSubscriptionRead",
    "WebhookSubscriptionUpdate",
]
