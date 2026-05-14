"""Users-admin service (Phase 1.6).

CRUD + role assignment + force-logout for the user table. Every mutation
appends a typed domain event via ``EventStore.append`` inside the same
transaction as the row write, so the wildcard audit-log projection picks
it up automatically.

Guards enforced at the service boundary (router maps them to 400s):

* An owner cannot deactivate themselves.
* An owner cannot demote themselves out of ``owner``.
* The last active owner cannot be deactivated.

Password generation
-------------------
``generate_password`` produces a 20-char string using ``secrets.choice``
over an alphabet that always contains upper-, lower-, digit, and symbol
character classes. The generator retries until at least one of each class
is present (probabilistically near-instant at length 20). Raw passwords
never appear in events, logs, or summaries — only on the response body
of the create / reset endpoints, exactly once.
"""

from __future__ import annotations

import secrets
import string
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import and_, asc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.events.types import users as users_events
from app.models.audit import AuditLog
from app.models.auth import Role, User
from app.schemas.events import EventCreate
from app.services import auth as auth_service
from app.services import event_store

# Password alphabet: every printable ASCII class is represented. Symbol
# set is intentionally pruned to avoid characters that get mangled by
# shells / copy-paste (no backtick, backslash, quote, space).
_PWD_UPPER = string.ascii_uppercase
_PWD_LOWER = string.ascii_lowercase
_PWD_DIGIT = string.digits
_PWD_SYMBOL = "!@#$%^&*()-_=+[]{}:;,.?/"
_PWD_ALPHABET = _PWD_UPPER + _PWD_LOWER + _PWD_DIGIT + _PWD_SYMBOL
GENERATED_PASSWORD_LENGTH = 20


class UsersServiceError(Exception):
    """Base for user-admin service errors. Routers map to 400."""


class SelfDeactivationError(UsersServiceError):
    pass


class SelfDemotionError(UsersServiceError):
    pass


class LastOwnerLockoutError(UsersServiceError):
    pass


class UserNotFoundError(UsersServiceError):
    pass


class DuplicateEmailError(UsersServiceError):
    pass


def generate_password(length: int = GENERATED_PASSWORD_LENGTH) -> str:
    """Return a freshly generated password.

    Guaranteed to contain at least one character from each class
    (upper, lower, digit, symbol). At length 20 with this alphabet the
    chance of needing a retry is vanishingly small, but the loop is
    correct regardless.
    """
    if length < 4:
        raise ValueError("password length must be >= 4 (one per class)")
    while True:
        chars = [secrets.choice(_PWD_ALPHABET) for _ in range(length)]
        if (
            any(c in _PWD_UPPER for c in chars)
            and any(c in _PWD_LOWER for c in chars)
            and any(c in _PWD_DIGIT for c in chars)
            and any(c in _PWD_SYMBOL for c in chars)
        ):
            return "".join(chars)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _count_active_owners(session: AsyncSession) -> int:
    stmt = (
        select(func.count())
        .select_from(User)
        .where(User.role == Role.OWNER, User.is_active.is_(True))
    )
    return int((await session.execute(stmt)).scalar_one())


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
            aggregate_type=users_events.AGGREGATE_TYPE,
            aggregate_id=aggregate_id,
            payload=payload,
            occurred_at=datetime.now(UTC),
            correlation_id=uuid.uuid4(),
            actor_user_id=actor_user_id,
        ),
        session=session,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


@dataclass
class CreatedUser:
    user: User
    generated_password: str


async def create_user(
    session: AsyncSession,
    *,
    actor: User,
    email: str,
    full_name: str,
    role: Role,
    bcrypt_rounds: int = 12,
) -> CreatedUser:
    """Create a user with an auto-generated initial password.

    The raw password is returned to the caller (router renders it once)
    and is NOT included in the emitted event payload.
    """
    normalized_email = email.strip().lower()
    existing = await session.execute(select(User.id).where(User.email == normalized_email))
    if existing.scalar_one_or_none() is not None:
        raise DuplicateEmailError(f"email {normalized_email!r} already exists")

    password = generate_password()
    user = User(
        email=normalized_email,
        password_hash=hash_password(password, rounds=bcrypt_rounds),
        full_name=full_name,
        role=role,
        is_active=True,
    )
    session.add(user)
    await session.flush()

    await _emit(
        session,
        event_type=users_events.TYPE_USER_CREATED,
        aggregate_id=user.id,
        payload={
            "user_id": str(user.id),
            "email": user.email,
            "full_name": user.full_name,
            "role": user.role.value,
        },
        actor_user_id=actor.id,
    )
    return CreatedUser(user=user, generated_password=password)


async def get_user(session: AsyncSession, user_id: uuid.UUID) -> User:
    user = await auth_service.get_user_by_id(session, user_id)
    if user is None:
        raise UserNotFoundError(str(user_id))
    return user


async def get_last_login(session: AsyncSession, user_id: uuid.UUID) -> datetime | None:
    """Most recent ``auth.LoginSucceeded`` event for the user from the
    audit_log read model, or None if there isn't one. Cheap lookup —
    audit_log is indexed on (event_type, actor_user_id).
    """
    from app.events.types.auth import TYPE_LOGIN_SUCCEEDED

    stmt = (
        select(AuditLog.occurred_at)
        .where(AuditLog.event_type == TYPE_LOGIN_SUCCEEDED)
        .where(AuditLog.actor_user_id == user_id)
        .order_by(AuditLog.occurred_at.desc())
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def update_user(
    session: AsyncSession,
    *,
    actor: User,
    user_id: uuid.UUID,
    full_name: str | None,
    role: Role | None,
    is_active: bool | None,
) -> User:
    """Patch the named fields on a user. Emits ``users.UserUpdated`` if
    anything actually changes.

    Guards:
      * actor demoting themselves out of owner → SelfDemotionError.
      * actor deactivating themselves → SelfDeactivationError.
      * deactivating the last active owner → LastOwnerLockoutError.
    """
    target = await get_user(session, user_id)

    if (
        role is not None
        and target.role == Role.OWNER
        and role != Role.OWNER
        and actor.id == target.id
    ):
        raise SelfDemotionError("an owner cannot demote themselves")

    if is_active is False and actor.id == target.id:
        raise SelfDeactivationError("an owner cannot deactivate themselves")

    # last-owner-lockout: either deactivation or demotion of the only
    # active owner is rejected.
    if target.role == Role.OWNER and (
        is_active is False or (role is not None and role != Role.OWNER)
    ):
        active_owners = await _count_active_owners(session)
        if active_owners <= 1:
            raise LastOwnerLockoutError("cannot deactivate or demote the last active owner")

    before: dict[str, Any] = {}
    after: dict[str, Any] = {}
    if full_name is not None and full_name != target.full_name:
        before["full_name"] = target.full_name
        after["full_name"] = full_name
        target.full_name = full_name
    if role is not None and role != target.role:
        before["role"] = target.role.value
        after["role"] = role.value
        target.role = role
    if is_active is not None and is_active != target.is_active:
        before["is_active"] = target.is_active
        after["is_active"] = is_active
        target.is_active = is_active

    if not before:
        # No-op update. Don't emit an event for a silent patch.
        return target

    await session.flush()

    # If the patch deactivated the user, also burn their refresh families.
    if "is_active" in after and after["is_active"] is False:
        await auth_service.revoke_all_families(
            session, user_id=target.id, reason="user_deactivated"
        )

    await _emit(
        session,
        event_type=users_events.TYPE_USER_UPDATED,
        aggregate_id=target.id,
        payload={
            "user_id": str(target.id),
            "before": before,
            "after": after,
        },
        actor_user_id=actor.id,
    )

    # If the user was deactivated by the patch we ALSO want a dedicated
    # UserDeactivated event in the log so audit consumers can filter on
    # the specific intent (vs a generic field-diff). Symmetric for
    # reactivation.
    if "is_active" in after:
        if after["is_active"] is False:
            await _emit(
                session,
                event_type=users_events.TYPE_USER_DEACTIVATED,
                aggregate_id=target.id,
                payload={
                    "user_id": str(target.id),
                    "reason": "admin_action",
                },
                actor_user_id=actor.id,
            )
        else:
            await _emit(
                session,
                event_type=users_events.TYPE_USER_REACTIVATED,
                aggregate_id=target.id,
                payload={"user_id": str(target.id)},
                actor_user_id=actor.id,
            )

    return target


async def deactivate_user(
    session: AsyncSession,
    *,
    actor: User,
    user_id: uuid.UUID,
) -> User:
    """Dedicated deactivate flow. Same guards as ``update_user`` for the
    is_active=False case, plus refresh-family revocation."""
    target = await get_user(session, user_id)

    if actor.id == target.id:
        raise SelfDeactivationError("an owner cannot deactivate themselves")

    if target.role == Role.OWNER:
        active_owners = await _count_active_owners(session)
        if active_owners <= 1 and target.is_active:
            raise LastOwnerLockoutError("cannot deactivate the last active owner")

    if not target.is_active:
        # Already inactive — return without re-emitting.
        return target

    target.is_active = False
    await session.flush()

    await auth_service.revoke_all_families(session, user_id=target.id, reason="user_deactivated")

    await _emit(
        session,
        event_type=users_events.TYPE_USER_DEACTIVATED,
        aggregate_id=target.id,
        payload={"user_id": str(target.id), "reason": "admin_action"},
        actor_user_id=actor.id,
    )
    return target


async def reactivate_user(
    session: AsyncSession,
    *,
    actor: User,
    user_id: uuid.UUID,
) -> User:
    target = await get_user(session, user_id)
    if target.is_active:
        return target
    target.is_active = True
    await session.flush()
    await _emit(
        session,
        event_type=users_events.TYPE_USER_REACTIVATED,
        aggregate_id=target.id,
        payload={"user_id": str(target.id)},
        actor_user_id=actor.id,
    )
    return target


@dataclass
class PasswordResetResult:
    user_id: uuid.UUID
    generated_password: str


async def reset_password(
    session: AsyncSession,
    *,
    actor: User,
    user_id: uuid.UUID,
    bcrypt_rounds: int = 12,
) -> PasswordResetResult:
    """Generate a new password, hash + store it, burn all refresh families."""
    target = await get_user(session, user_id)
    new_password = generate_password()
    target.password_hash = hash_password(new_password, rounds=bcrypt_rounds)
    await session.flush()

    await auth_service.revoke_all_families(
        session, user_id=target.id, reason="admin_password_reset"
    )

    await _emit(
        session,
        event_type=users_events.TYPE_PASSWORD_RESET_BY_ADMIN,
        aggregate_id=target.id,
        payload={
            "user_id": str(target.id),
            "reset_by_user_id": str(actor.id),
        },
        actor_user_id=actor.id,
    )
    return PasswordResetResult(user_id=target.id, generated_password=new_password)


# ---------------------------------------------------------------------------
# List / pagination
# ---------------------------------------------------------------------------


@dataclass
class UserPage:
    items: list[User]
    next_cursor: str | None


def _encode_cursor(created_at: datetime, user_id: uuid.UUID) -> str:
    import base64
    import json

    raw = json.dumps({"c": created_at.isoformat(), "i": str(user_id)}).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii")


def _decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    import base64
    import json

    try:
        raw = base64.urlsafe_b64decode(cursor.encode("ascii"))
        decoded = json.loads(raw.decode("utf-8"))
        return datetime.fromisoformat(decoded["c"]), uuid.UUID(decoded["i"])
    except (ValueError, KeyError, TypeError) as exc:
        raise UsersServiceError(f"invalid cursor: {exc}") from exc


async def list_users(
    session: AsyncSession,
    *,
    search: str | None = None,
    role: Role | None = None,
    is_active: bool | None = None,
    limit: int = 50,
    cursor: str | None = None,
) -> UserPage:
    stmt = select(User)
    if search:
        pattern = f"%{search.lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(User.email).like(pattern),
                func.lower(User.full_name).like(pattern),
            )
        )
    if role is not None:
        stmt = stmt.where(User.role == role)
    if is_active is not None:
        stmt = stmt.where(User.is_active.is_(is_active))
    if cursor is not None:
        anchor_ts, anchor_id = _decode_cursor(cursor)
        stmt = stmt.where(
            or_(
                User.created_at > anchor_ts,
                and_(User.created_at == anchor_ts, User.id > anchor_id),
            )
        )
    stmt = stmt.order_by(asc(User.created_at), asc(User.id)).limit(limit + 1)
    rows = list((await session.execute(stmt)).scalars().all())
    has_more = len(rows) > limit
    if has_more:
        rows = rows[:limit]
    next_cursor = _encode_cursor(rows[-1].created_at, rows[-1].id) if (rows and has_more) else None
    return UserPage(items=rows, next_cursor=next_cursor)
