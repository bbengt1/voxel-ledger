"""Password hashing, JWT encode/decode, refresh-token helpers.

Pure functions. State (DB, request) lives in services and routers; this
module is just the crypto/encoding primitives.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from passlib.context import CryptContext

from app.core.settings import Settings

_pwd_context_cache: dict[int, CryptContext] = {}


def _pwd_context(rounds: int) -> CryptContext:
    """Cache one CryptContext per round count; passlib bcrypt setup isn't
    free and tests run with rounds=4 to stay fast."""
    ctx = _pwd_context_cache.get(rounds)
    if ctx is None:
        ctx = CryptContext(schemes=["bcrypt"], deprecated="auto", bcrypt__rounds=rounds)
        _pwd_context_cache[rounds] = ctx
    return ctx


def hash_password(password: str, rounds: int = 12) -> str:
    return _pwd_context(rounds).hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    # passlib bcrypt is forgiving on rounds at verify time — it reads them
    # from the stored hash.
    try:
        return _pwd_context(12).verify(password, password_hash)
    except (ValueError, TypeError):
        return False


def create_access_token(
    *,
    settings: Settings,
    user_id: uuid.UUID,
    role: str,
    now: datetime | None = None,
) -> str:
    """Encode a short-lived JWT carrying user id, role, and standard claims."""
    issued = now or datetime.now(UTC)
    expires = issued + timedelta(seconds=settings.access_token_ttl_seconds)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "role": role,
        "iat": int(issued.timestamp()),
        "exp": int(expires.timestamp()),
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str, settings: Settings) -> dict[str, Any]:
    """Decode + verify the JWT. Raises jwt.PyJWTError on failure."""
    return jwt.decode(
        token,
        settings.jwt_secret_key,
        algorithms=[settings.jwt_algorithm],
    )


def generate_refresh_token() -> tuple[str, str]:
    """Return (raw_token, sha256_hex_hash). Raw is sent to the client; only
    the hash hits the DB."""
    raw = secrets.token_urlsafe(32)
    return raw, hash_refresh_token(raw)


def hash_refresh_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
