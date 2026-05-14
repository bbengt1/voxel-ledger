"""Auth endpoints: login, refresh, logout, me.

Thin layer over `app.services.auth`. Rate limit + audit hooks live here
because they're crosscut concerns, not domain logic.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_settings
from app.core.db import get_session
from app.core.rate_limit import InMemoryRateLimiter, client_ip
from app.core.settings import Settings
from app.models.auth import User
from app.schemas.auth import (
    LoginRequest,
    LogoutRequest,
    MeResponse,
    RefreshRequest,
    TokenPair,
)
from app.services import auth as auth_service
from app.services.audit import log_auth_event

router = APIRouter(prefix="/auth", tags=["auth"])

# Module-level limiter; capacity = LOGIN_RATE_LIMIT_PER_MINUTE, refill 1/min/N.
# Constructed lazily so settings can change between test runs.
_login_limiter: InMemoryRateLimiter | None = None
_login_limiter_capacity: int | None = None


def _get_login_limiter(settings: Settings) -> InMemoryRateLimiter:
    global _login_limiter, _login_limiter_capacity
    if (
        _login_limiter is None
        or _login_limiter_capacity != settings.login_rate_limit_per_minute
    ):
        capacity = settings.login_rate_limit_per_minute
        _login_limiter = InMemoryRateLimiter(
            capacity=capacity, rate_per_sec=capacity / 60.0
        )
        _login_limiter_capacity = capacity
    return _login_limiter


def reset_login_limiter() -> None:
    """Test hook — drop in-memory state between cases."""
    global _login_limiter, _login_limiter_capacity
    _login_limiter = None
    _login_limiter_capacity = None


@router.post("/login", response_model=TokenPair)
async def login(
    payload: LoginRequest,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> TokenPair:
    ip = client_ip(request)
    limiter = _get_login_limiter(settings)
    if not limiter.allow(ip):
        log_auth_event("auth.login.rate_limited", ip=ip)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="too many login attempts",
        )

    try:
        tokens = await auth_service.login(
            session,
            email=payload.email,
            password=payload.password,
            settings=settings,
        )
    except auth_service.InvalidCredentialsError:
        log_auth_event("auth.login.failed", ip=ip, extra={"email": payload.email})
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid credentials"
        ) from None
    except auth_service.InactiveUserError:
        log_auth_event(
            "auth.login.inactive", ip=ip, extra={"email": payload.email}
        )
        # Same response shape as bad creds — don't leak account state.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid credentials"
        ) from None

    await session.commit()
    log_auth_event("auth.login.success", user_id=tokens.user.id, ip=ip)
    return TokenPair(
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        expires_in=tokens.expires_in,
    )


@router.post("/refresh", response_model=TokenPair)
async def refresh(
    payload: RefreshRequest,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> TokenPair:
    ip = client_ip(request)
    try:
        tokens = await auth_service.rotate_refresh_token(
            session,
            presented_token=payload.refresh_token,
            settings=settings,
        )
    except auth_service.ReuseDetectedError:
        await session.commit()  # persist the family revocation
        log_auth_event("auth.refresh.reuse_detected", ip=ip)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="refresh token reused"
        ) from None
    except auth_service.InvalidRefreshTokenError:
        log_auth_event("auth.refresh.invalid", ip=ip)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid refresh token"
        ) from None

    await session.commit()
    log_auth_event("auth.refresh.success", user_id=tokens.user.id, ip=ip)
    return TokenPair(
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        expires_in=tokens.expires_in,
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    payload: LogoutRequest,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> None:
    ip = client_ip(request)
    user_id = await auth_service.logout(
        session, presented_token=payload.refresh_token
    )
    await session.commit()
    log_auth_event("auth.logout", user_id=user_id, ip=ip)


@router.get("/me", response_model=MeResponse)
async def me(user: Annotated[User, Depends(get_current_user)]) -> MeResponse:
    return MeResponse.model_validate(user)
