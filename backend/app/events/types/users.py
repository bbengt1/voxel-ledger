"""Users-bounded-context event types (Phase 1.6).

Every user-admin mutation is a domain event in the log: creation,
profile/role updates, deactivation, reactivation, and admin password
reset. The audit-log projection materializes each into a row.

Aggregate type is ``user``; aggregate_id is the target user's id.
``actor_user_id`` on the event row is the admin performing the action.

Payloads MUST NOT contain raw passwords or password hashes. The excerpt
whitelist enforces this at the read-model boundary, but the payload model
is the first line of defense — none of these models declare a password
field, and the registry rejects extras (``extra='forbid'``).
"""

from __future__ import annotations

import uuid
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from app.events.registry import register_event

AGGREGATE_TYPE: str = "user"


class _UserPayloadBase(BaseModel):
    model_config = ConfigDict(extra="forbid")


class UserCreatedPayload(_UserPayloadBase):
    user_id: uuid.UUID
    email: str
    full_name: str
    role: str


class UserUpdatedPayload(_UserPayloadBase):
    user_id: uuid.UUID
    # Only changed fields. Values are JSON-serializable scalars (str/bool/None).
    before: dict[str, Any]
    after: dict[str, Any]


class UserDeactivatedPayload(_UserPayloadBase):
    user_id: uuid.UUID
    reason: Literal["admin_action"] = "admin_action"


class UserReactivatedPayload(_UserPayloadBase):
    user_id: uuid.UUID


class PasswordResetByAdminPayload(_UserPayloadBase):
    user_id: uuid.UUID
    reset_by_user_id: uuid.UUID


TYPE_USER_CREATED = "users.UserCreated"
TYPE_USER_UPDATED = "users.UserUpdated"
TYPE_USER_DEACTIVATED = "users.UserDeactivated"
TYPE_USER_REACTIVATED = "users.UserReactivated"
TYPE_PASSWORD_RESET_BY_ADMIN = "users.PasswordResetByAdmin"


register_event(TYPE_USER_CREATED, UserCreatedPayload)
register_event(TYPE_USER_UPDATED, UserUpdatedPayload)
register_event(TYPE_USER_DEACTIVATED, UserDeactivatedPayload)
register_event(TYPE_USER_REACTIVATED, UserReactivatedPayload)
register_event(TYPE_PASSWORD_RESET_BY_ADMIN, PasswordResetByAdminPayload)
