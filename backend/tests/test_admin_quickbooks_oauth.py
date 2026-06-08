"""Admin QuickBooks OAuth endpoints + service (#314, epic #312).

Covers: role matrix, connect URL (+ unconfigured 400), OAuth callback happy /
bad-state / missing-param paths, disconnect, enabled toggle, status token-health
without leaking secrets, refresh-token rotation persistence, and OpenAPI
registration. intuitlib is never touched — the `_build_auth_client` /
`build_authorization_url` seams are monkeypatched.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from app.core.settings import Settings
from app.models.auth import Role, User
from app.models.oauth_credential import OAuthCredential, OAuthProvider
from app.services.auth import create_user
from app.services.quickbooks import oauth
from app.services.settings.service import SettingsService
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

QB = "/api/v1/admin/quickbooks"


class FakeAuthClient:
    """Stand-in for intuitlib AuthClient. Rotates the refresh token on refresh."""

    def __init__(self, **kwargs: object) -> None:
        self.realm_id = kwargs.get("realm_id")
        self.access_token = kwargs.get("access_token") or "init-access"
        self.refresh_token = kwargs.get("refresh_token") or "init-refresh"
        self.expires_in = 3600
        self.x_refresh_token_expires_in = 8_640_000
        self.revoked: str | None = None

    def get_bearer_token(self, code: str, realm_id: str | None = None) -> None:
        self.access_token = f"acc-{code}"
        self.refresh_token = f"ref-{code}"
        self.realm_id = realm_id or self.realm_id

    def refresh(self, refresh_token: str | None = None) -> None:
        self.access_token = "refreshed-access"
        self.refresh_token = "rotated-refresh"  # rotation
        self.expires_in = 3600
        self.x_refresh_token_expires_in = 8_640_000

    def revoke(self, token: str | None = None) -> None:
        self.revoked = token


def _fake_factory(settings: Settings, **kwargs: object) -> FakeAuthClient:
    return FakeAuthClient(**kwargs)


async def _seed(role: Role, client: AsyncClient, session: AsyncSession) -> tuple[str, User]:
    email = f"{role.value}@example.com"
    user = await create_user(
        session,
        email=email,
        password="pw-correct",
        full_name=role.value,
        role=role,
        bcrypt_rounds=4,
    )
    await session.commit()
    r = await client.post("/api/v1/auth/login", json={"email": email, "password": "pw-correct"})
    return r.json()["access_token"], user


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _insert_credential(session: AsyncSession, **overrides: object) -> OAuthCredential:
    now = datetime.now(UTC)
    cred = OAuthCredential(
        provider=OAuthProvider.QUICKBOOKS.value,
        realm_id="4620816365",
        access_token="supersecret-access-token",
        refresh_token="supersecret-refresh-token",
        access_token_expires_at=now + timedelta(hours=1),
        refresh_token_expires_at=now + timedelta(days=100),
        scope=oauth.ACCOUNTING_SCOPE,
    )
    for key, value in overrides.items():
        setattr(cred, key, value)
    session.add(cred)
    await session.commit()
    return cred


# --------------------------------------------------------------------------- #
# auth / role matrix
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_status_requires_auth(client: AsyncClient) -> None:
    r = await client.get(f"{QB}/status")
    assert r.status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "role,expected",
    [
        (Role.OWNER, 200),
        (Role.BOOKKEEPER, 403),
        (Role.PRODUCTION, 403),
        (Role.SALES, 403),
        (Role.VIEWER, 403),
    ],
)
async def test_status_role_matrix(
    client: AsyncClient, app_session: AsyncSession, role: Role, expected: int
) -> None:
    token, _ = await _seed(role, client, app_session)
    r = await client.get(f"{QB}/status", headers=_auth(token))
    assert r.status_code == expected, r.text


# --------------------------------------------------------------------------- #
# status
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_status_disconnected(client: AsyncClient, app_session: AsyncSession) -> None:
    token, _ = await _seed(Role.OWNER, client, app_session)
    r = await client.get(f"{QB}/status", headers=_auth(token))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["connected"] is False
    assert body["enabled"] is False
    assert body["environment"] == "sandbox"
    assert body["realm_id"] is None


@pytest.mark.asyncio
async def test_status_connected_never_leaks_tokens(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    token, _ = await _seed(Role.OWNER, client, app_session)
    await _insert_credential(app_session)
    r = await client.get(f"{QB}/status", headers=_auth(token))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["connected"] is True
    assert body["realm_id"] == "4620816365"
    assert body["token_health"] == oauth.HEALTH_OK
    # No token value or token-bearing key may appear in the response.
    assert "supersecret" not in r.text
    assert "access_token" not in body
    assert "refresh_token" not in body


@pytest.mark.asyncio
async def test_status_token_health_reconnect_required(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    token, _ = await _seed(Role.OWNER, client, app_session)
    past = datetime.now(UTC) - timedelta(days=1)
    await _insert_credential(
        app_session, access_token_expires_at=past, refresh_token_expires_at=past
    )
    r = await client.get(f"{QB}/status", headers=_auth(token))
    assert r.json()["token_health"] == oauth.HEALTH_RECONNECT_REQUIRED


# --------------------------------------------------------------------------- #
# connect
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_connect_returns_authorization_url(
    client: AsyncClient, app_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    token, _ = await _seed(Role.OWNER, client, app_session)
    monkeypatch.setattr(oauth, "require_config", lambda settings: None)
    monkeypatch.setattr(
        oauth,
        "build_authorization_url",
        lambda settings, *, state: f"https://appcenter.intuit.com/connect/oauth2?state={state}",
    )
    r = await client.get(f"{QB}/connect", headers=_auth(token))
    assert r.status_code == 200, r.text
    assert r.json()["authorization_url"].startswith("https://appcenter.intuit.com/connect/oauth2")


@pytest.mark.asyncio
async def test_connect_unconfigured_returns_400(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    # Default test settings have no QBO creds, so require_config raises.
    token, _ = await _seed(Role.OWNER, client, app_session)
    r = await client.get(f"{QB}/connect", headers=_auth(token))
    assert r.status_code == 400
    assert "not configured" in r.json()["detail"]


# --------------------------------------------------------------------------- #
# callback
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_callback_happy_path_persists_and_redirects(
    client: AsyncClient,
    app_session: AsyncSession,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, owner = await _seed(Role.OWNER, client, app_session)
    monkeypatch.setattr(oauth, "_build_auth_client", _fake_factory)
    state = oauth.issue_state(settings, actor_user_id=owner.id)

    r = await client.get(
        f"{QB}/callback",
        params={"code": "AUTHCODE", "realmId": "9999", "state": state},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert r.headers["location"] == "/admin/quickbooks?connected=1"

    cred = (
        await app_session.execute(
            select(OAuthCredential).where(
                OAuthCredential.provider == OAuthProvider.QUICKBOOKS.value
            )
        )
    ).scalar_one()
    assert cred.realm_id == "9999"
    assert cred.access_token == "acc-AUTHCODE"
    assert cred.refresh_token == "ref-AUTHCODE"
    # realm id mirrored into settings
    assert await SettingsService.get("quickbooks.realm_id", session=app_session) == "9999"


@pytest.mark.asyncio
async def test_callback_bad_state_redirects_with_error_and_persists_nothing(
    client: AsyncClient, app_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _seed(Role.OWNER, client, app_session)
    monkeypatch.setattr(oauth, "_build_auth_client", _fake_factory)
    r = await client.get(
        f"{QB}/callback",
        params={"code": "X", "realmId": "9999", "state": "not-a-valid-jwt"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert "error=" in r.headers["location"]
    count = (await app_session.execute(select(OAuthCredential))).scalars().all()
    assert count == []


@pytest.mark.asyncio
async def test_callback_missing_params_redirects_with_error(client: AsyncClient) -> None:
    r = await client.get(f"{QB}/callback", params={"code": "X"}, follow_redirects=False)
    assert r.status_code == 303
    assert "error=missing_oauth_params" in r.headers["location"]


# --------------------------------------------------------------------------- #
# disconnect
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_disconnect_revokes_clears_and_disables(
    client: AsyncClient, app_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    token, owner = await _seed(Role.OWNER, client, app_session)
    await _insert_credential(app_session)
    await SettingsService.set(
        "quickbooks.enabled", True, session=app_session, actor_user_id=owner.id
    )
    await app_session.commit()
    monkeypatch.setattr(oauth, "_build_auth_client", _fake_factory)

    r = await client.post(f"{QB}/disconnect", headers=_auth(token))
    assert r.status_code == 204, r.text

    remaining = (await app_session.execute(select(OAuthCredential))).scalars().all()
    assert remaining == []
    assert await SettingsService.get("quickbooks.enabled", session=app_session) is False
    assert await SettingsService.get("quickbooks.realm_id", session=app_session) is None


@pytest.mark.asyncio
async def test_disconnect_is_idempotent_when_not_connected(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    token, _ = await _seed(Role.OWNER, client, app_session)
    r = await client.post(f"{QB}/disconnect", headers=_auth(token))
    assert r.status_code == 204


# --------------------------------------------------------------------------- #
# enabled toggle
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_set_enabled_persists(client: AsyncClient, app_session: AsyncSession) -> None:
    token, _ = await _seed(Role.OWNER, client, app_session)
    r = await client.post(f"{QB}/enabled", headers=_auth(token), json={"enabled": True})
    assert r.status_code == 200, r.text
    assert r.json()["enabled"] is True
    assert await SettingsService.get("quickbooks.enabled", session=app_session) is True


@pytest.mark.asyncio
async def test_set_enabled_requires_owner(client: AsyncClient, app_session: AsyncSession) -> None:
    token, _ = await _seed(Role.BOOKKEEPER, client, app_session)
    r = await client.post(f"{QB}/enabled", headers=_auth(token), json={"enabled": True})
    assert r.status_code == 403


# --------------------------------------------------------------------------- #
# service: refresh-token rotation persistence (Phase-0 rule)
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_ensure_fresh_access_token_rotates_and_persists(
    client: AsyncClient,
    app_session: AsyncSession,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Access token already expired → ensure_fresh must refresh.
    past = datetime.now(UTC) - timedelta(minutes=1)
    await _insert_credential(
        app_session, access_token_expires_at=past, refresh_token="orig-refresh"
    )
    monkeypatch.setattr(oauth, "_build_auth_client", _fake_factory)

    cred = await oauth.ensure_fresh_access_token(app_session, settings)
    assert cred.access_token == "refreshed-access"
    # The rotated refresh token must be persisted (not the original).
    assert cred.refresh_token == "rotated-refresh"
    assert cred.access_token_expires_at > datetime.now(UTC)


@pytest.mark.asyncio
async def test_ensure_fresh_access_token_not_connected_raises(
    client: AsyncClient, app_session: AsyncSession, settings: Settings
) -> None:
    with pytest.raises(oauth.QuickBooksNotConnectedError):
        await oauth.ensure_fresh_access_token(app_session, settings)


# --------------------------------------------------------------------------- #
# OpenAPI registration (frontend codegen)
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_endpoints_in_openapi(client: AsyncClient) -> None:
    r = await client.get("/api/v1/openapi.json")
    paths = r.json()["paths"]
    assert f"{QB}/status" in paths
    assert f"{QB}/connect" in paths
    assert f"{QB}/disconnect" in paths
    assert f"{QB}/enabled" in paths
    # callback is include_in_schema=False
    assert f"{QB}/callback" not in paths
