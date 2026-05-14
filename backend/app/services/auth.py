"""Auth service layer.

All business logic for login, refresh rotation, logout, and the reuse-
detection family revocation lives here. Routers stay thin.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import (
    create_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)
from app.core.settings import Settings
from app.models.auth import RefreshToken, Role, User


class AuthError(Exception):
    """Base class for auth-flow errors. Routers translate to 401/403."""


class InvalidCredentialsError(AuthError):
    pass


class InactiveUserError(AuthError):
    pass


class InvalidRefreshTokenError(AuthError):
    pass


class ReuseDetectedError(AuthError):
    """The presented refresh token was already revoked. Family was burned."""


@dataclass
class IssuedTokens:
    access_token: str
    refresh_token: str
    expires_in: int
    user: User


async def create_user(
    session: AsyncSession,
    *,
    email: str,
    password: str,
    full_name: str,
    role: Role,
    bcrypt_rounds: int = 12,
    is_active: bool = True,
) -> User:
    """Insert a new user with a freshly hashed password."""
    user = User(
        email=email.strip().lower(),
        password_hash=hash_password(password, rounds=bcrypt_rounds),
        full_name=full_name,
        role=role,
        is_active=is_active,
    )
    session.add(user)
    await session.flush()
    return user


async def get_user_by_email(session: AsyncSession, email: str) -> User | None:
    stmt = select(User).where(User.email == email.strip().lower())
    return (await session.execute(stmt)).scalar_one_or_none()


async def get_user_by_id(session: AsyncSession, user_id: uuid.UUID) -> User | None:
    stmt = select(User).where(User.id == user_id)
    return (await session.execute(stmt)).scalar_one_or_none()


async def authenticate(
    session: AsyncSession,
    *,
    email: str,
    password: str,
) -> User:
    """Look up + verify a user. Same error for missing user vs wrong password
    so we don't leak which one was wrong."""
    user = await get_user_by_email(session, email)
    if user is None:
        raise InvalidCredentialsError("invalid credentials")
    if not verify_password(password, user.password_hash):
        raise InvalidCredentialsError("invalid credentials")
    if not user.is_active:
        raise InactiveUserError("account inactive")
    return user


async def _persist_refresh_token(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    family_id: uuid.UUID,
    parent_token_id: uuid.UUID | None,
    token_hash: str,
    ttl_seconds: int,
    now: datetime,
) -> RefreshToken:
    row = RefreshToken(
        user_id=user_id,
        family_id=family_id,
        parent_token_id=parent_token_id,
        token_hash=token_hash,
        issued_at=now,
        expires_at=now + timedelta(seconds=ttl_seconds),
    )
    session.add(row)
    await session.flush()
    return row


async def issue_tokens_for_user(
    session: AsyncSession,
    *,
    user: User,
    settings: Settings,
    family_id: uuid.UUID | None = None,
    parent_token_id: uuid.UUID | None = None,
) -> IssuedTokens:
    """Mint a new access JWT + refresh token. Records the refresh token row
    in the given family (or starts a new family if `family_id` is None)."""
    now = datetime.now(UTC)
    raw, token_hash = generate_refresh_token()
    family = family_id or uuid.uuid4()
    await _persist_refresh_token(
        session,
        user_id=user.id,
        family_id=family,
        parent_token_id=parent_token_id,
        token_hash=token_hash,
        ttl_seconds=settings.refresh_token_ttl_seconds,
        now=now,
    )
    access = create_access_token(settings=settings, user_id=user.id, role=user.role.value, now=now)
    return IssuedTokens(
        access_token=access,
        refresh_token=raw,
        expires_in=settings.access_token_ttl_seconds,
        user=user,
    )


async def login(
    session: AsyncSession,
    *,
    email: str,
    password: str,
    settings: Settings,
) -> IssuedTokens:
    user = await authenticate(session, email=email, password=password)
    tokens = await issue_tokens_for_user(session, user=user, settings=settings)
    return tokens


async def _revoke_family(
    session: AsyncSession,
    *,
    family_id: uuid.UUID,
    reason: str,
    now: datetime,
) -> None:
    """Revoke every non-revoked row in a family in one statement."""
    stmt = (
        update(RefreshToken)
        .where(RefreshToken.family_id == family_id)
        .where(RefreshToken.revoked_at.is_(None))
        .values(revoked_at=now, revocation_reason=reason)
    )
    await session.execute(stmt)


async def rotate_refresh_token(
    session: AsyncSession,
    *,
    presented_token: str,
    settings: Settings,
) -> IssuedTokens:
    """Validate the presented refresh token and rotate to a fresh pair.

    Reuse detection: if the presented token is already revoked, the whole
    family is burned and we raise ReuseDetectedError.
    """
    presented_hash = hash_refresh_token(presented_token)
    stmt = select(RefreshToken).where(RefreshToken.token_hash == presented_hash)
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise InvalidRefreshTokenError("unknown refresh token")

    now = datetime.now(UTC)

    expires_at = row.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)

    if row.revoked_at is not None:
        # Reuse — burn the whole family.
        await _revoke_family(session, family_id=row.family_id, reason="reuse_detected", now=now)
        await session.flush()
        raise ReuseDetectedError("refresh token reuse detected")

    if expires_at <= now:
        # Expired tokens don't trigger family revocation, just rejection.
        raise InvalidRefreshTokenError("refresh token expired")

    user = await get_user_by_id(session, row.user_id)
    if user is None or not user.is_active:
        raise InvalidRefreshTokenError("user no longer active")

    # Mark the presented token as rotated.
    row.revoked_at = now
    row.revocation_reason = "rotated"
    await session.flush()

    return await issue_tokens_for_user(
        session,
        user=user,
        settings=settings,
        family_id=row.family_id,
        parent_token_id=row.id,
    )


async def logout(
    session: AsyncSession,
    *,
    presented_token: str,
) -> uuid.UUID | None:
    """Revoke the family the presented token belongs to. Returns the
    user_id whose family was burned, or None if the token is unknown."""
    presented_hash = hash_refresh_token(presented_token)
    stmt = select(RefreshToken).where(RefreshToken.token_hash == presented_hash)
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        return None
    now = datetime.now(UTC)
    await _revoke_family(session, family_id=row.family_id, reason="logout", now=now)
    await session.flush()
    return row.user_id
