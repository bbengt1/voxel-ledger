"""Auth-bounded-context event types (Phase 1.4).

Every meaningful auth outcome is an event in the log: login attempts (good
and bad), refresh rotations, family revocations on reuse, logouts, and
rate-limit hits. The audit-log projection turns each of these into a row
in ``audit_log``.

The aggregate for auth events is always the ``user`` aggregate. For
events where we don't have (or shouldn't claim) a specific user — failed
logins for unknown emails, anonymous rate limiting — the ``aggregate_id``
is a zero UUID sentinel. The projection still gets a row; the actor just
isn't resolved.

Payloads MUST NOT contain raw tokens, password hashes, or session IDs.
The excerpt whitelist enforces this at the read-model boundary, but the
payload model is the first line of defense.
"""

from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.events.registry import register_event

# Sentinel for "no specific user aggregate" (anonymous events: rate-limit
# trips, failed login on unknown email). The audit projection still writes
# a row; the actor column is just null.
ANONYMOUS_AGGREGATE_ID: uuid.UUID = uuid.UUID("00000000-0000-0000-0000-000000000000")

AGGREGATE_TYPE: str = "user"


class _AuthPayloadBase(BaseModel):
    """Common base: every auth event optionally carries the caller IP.

    IP is folded into the payload (rather than a dedicated event column)
    so the projection can denormalize it without per-event-type knowledge,
    and so we don't have to widen the event row schema for a single
    bounded context.
    """

    # Strict by default — extra fields rejected so a typo in a call site
    # surfaces at append time, not silently in the read model.
    model_config = ConfigDict(extra="forbid")

    ip: str | None = None


class LoginSucceededPayload(_AuthPayloadBase):
    email: str
    user_id: uuid.UUID


class LoginFailedPayload(_AuthPayloadBase):
    email: str
    reason: Literal["unknown_user", "bad_password"]


class LoginInactivePayload(_AuthPayloadBase):
    email: str


class RefreshRotatedPayload(_AuthPayloadBase):
    user_id: uuid.UUID


class FamilyRevokedPayload(_AuthPayloadBase):
    """Refresh-token reuse detected → entire family burned."""

    reason: Literal["reuse_detected", "invalid_refresh"]
    user_id: uuid.UUID | None = None


class LoggedOutPayload(_AuthPayloadBase):
    user_id: uuid.UUID | None = None


class RateLimitedPayload(_AuthPayloadBase):
    endpoint: Literal["login"]


# Type strings. Kept as module-level constants so call sites import the
# canonical spelling rather than hard-coding it.
TYPE_LOGIN_SUCCEEDED = "auth.LoginSucceeded"
TYPE_LOGIN_FAILED = "auth.LoginFailed"
TYPE_LOGIN_INACTIVE = "auth.LoginInactive"
TYPE_REFRESH_ROTATED = "auth.RefreshRotated"
TYPE_FAMILY_REVOKED = "auth.FamilyRevoked"
TYPE_LOGGED_OUT = "auth.LoggedOut"
TYPE_RATE_LIMITED = "auth.RateLimited"


register_event(TYPE_LOGIN_SUCCEEDED, LoginSucceededPayload)
register_event(TYPE_LOGIN_FAILED, LoginFailedPayload)
register_event(TYPE_LOGIN_INACTIVE, LoginInactivePayload)
register_event(TYPE_REFRESH_ROTATED, RefreshRotatedPayload)
register_event(TYPE_FAMILY_REVOKED, FamilyRevokedPayload)
register_event(TYPE_LOGGED_OUT, LoggedOutPayload)
register_event(TYPE_RATE_LIMITED, RateLimitedPayload)
