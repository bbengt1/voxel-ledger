"""Admin endpoints for the QuickBooks Online connection (#314, epic #312).

Owner-only. Mounted under ``/api/v1/admin/quickbooks``.

* ``GET  /connect``    → returns the Intuit consent URL (frontend redirects).
* ``GET  /callback``   → **unauthenticated**, state-validated; Intuit redirects
  the browser here, so it can't carry our bearer token. Exchanges the code,
  persists tokens, then redirects back into the SPA.
* ``POST /disconnect`` → revoke + delete credential, disable sync.
* ``GET  /status``     → connection + token health (never any token value).
* ``POST /enabled``    → flip ``quickbooks.enabled`` (no effect until Phase 3).
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_settings, require_role
from app.core.db import get_session
from app.core.settings import Settings
from app.models.auth import User
from app.services.quickbooks import oauth
from app.services.settings.service import SettingsService

router = APIRouter(prefix="/quickbooks", tags=["admin-quickbooks"])

# Where the OAuth callback sends the browser back to (SPA route).
_FRONTEND_RETURN = "/admin/quickbooks"


class QuickBooksStatusResponse(BaseModel):
    connected: bool
    enabled: bool
    environment: str
    realm_id: str | None = None
    token_health: str | None = None  # ok | access_expired | reconnect_required
    access_token_expires_at: datetime | None = None
    refresh_token_expires_at: datetime | None = None


class ConnectResponse(BaseModel):
    authorization_url: str


class EnabledRequest(BaseModel):
    enabled: bool


async def _status_payload(session: AsyncSession, settings: Settings) -> QuickBooksStatusResponse:
    enabled = bool(await SettingsService.get("quickbooks.enabled", session=session))
    cred = await oauth.get_credential(session)
    if cred is None:
        return QuickBooksStatusResponse(
            connected=False, enabled=enabled, environment=settings.qbo_environment
        )
    return QuickBooksStatusResponse(
        connected=True,
        enabled=enabled,
        environment=settings.qbo_environment,
        realm_id=cred.realm_id,
        token_health=oauth.token_health(cred),
        access_token_expires_at=cred.access_token_expires_at,
        refresh_token_expires_at=cred.refresh_token_expires_at,
    )


@router.get("/status", response_model=QuickBooksStatusResponse)
async def quickbooks_status(
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    _user: Annotated[User, Depends(require_role("owner"))],
) -> QuickBooksStatusResponse:
    return await _status_payload(session, settings)


@router.get("/connect", response_model=ConnectResponse)
async def quickbooks_connect(
    settings: Annotated[Settings, Depends(get_settings)],
    user: Annotated[User, Depends(require_role("owner"))],
) -> ConnectResponse:
    try:
        oauth.require_config(settings)
        state = oauth.issue_state(settings, actor_user_id=user.id)
        url = oauth.build_authorization_url(settings, state=state)
    except oauth.QuickBooksConfigError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return ConnectResponse(authorization_url=url)


@router.get("/callback", include_in_schema=False)
async def quickbooks_callback(
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    code: Annotated[str | None, Query()] = None,
    realmId: Annotated[str | None, Query()] = None,
    state: Annotated[str | None, Query()] = None,
    error: Annotated[str | None, Query()] = None,
) -> RedirectResponse:
    # No auth dependency: Intuit redirects the browser here without our bearer.
    # Authenticity comes from the signed `state` issued at /connect.
    if error:
        return RedirectResponse(f"{_FRONTEND_RETURN}?error={quote(error)}", status_code=303)
    if not code or not realmId or not state:
        return RedirectResponse(f"{_FRONTEND_RETURN}?error=missing_oauth_params", status_code=303)
    try:
        actor_user_id = oauth.verify_state(settings, state)
        await oauth.complete_authorization(
            session, settings, code=code, realm_id=realmId, actor_user_id=actor_user_id
        )
        await session.commit()
    except oauth.QuickBooksOAuthError as exc:
        await session.rollback()
        return RedirectResponse(f"{_FRONTEND_RETURN}?error={quote(str(exc))}", status_code=303)
    return RedirectResponse(f"{_FRONTEND_RETURN}?connected=1", status_code=303)


@router.post("/disconnect", status_code=status.HTTP_204_NO_CONTENT)
async def quickbooks_disconnect(
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    user: Annotated[User, Depends(require_role("owner"))],
) -> Response:
    await oauth.disconnect(session, settings, actor_user_id=user.id)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/enabled", response_model=QuickBooksStatusResponse)
async def quickbooks_set_enabled(
    body: EnabledRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    user: Annotated[User, Depends(require_role("owner"))],
) -> QuickBooksStatusResponse:
    await SettingsService.set(
        "quickbooks.enabled", body.enabled, session=session, actor_user_id=user.id
    )
    await session.commit()
    return await _status_payload(session, settings)
