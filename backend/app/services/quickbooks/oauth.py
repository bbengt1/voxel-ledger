"""QuickBooks Online OAuth 2.0 — connect, refresh, disconnect (#314, epic #312).

Implements the authorization-code flow against Intuit using the official
``intuit-oauth`` (intuitlib) client, and persists tokens in the
``oauth_credential`` table. All Phase-0-verified rules
(``docs/quickbooks_phase0_findings.md``) are honored:

* access token ≈ 1 h (``expires_in`` 3600), refresh token 100-day rolling.
* **Always persist the latest ``refresh_token`` from every response** — the
  refresh token rotates; reusing a stale one breaks the chain.
* a broken refresh chain surfaces as :class:`QuickBooksOAuthError` →
  "reconnect required".

intuitlib is imported lazily inside :func:`_build_auth_client` /
:func:`build_authorization_url` so unit tests can monkeypatch those seams
without the library (or network) present.

CSRF: the ``state`` round-tripped through Intuit is a short-lived HS256 JWT
signed with the app's ``jwt_secret_key`` and carrying the initiating owner's
user id. The unauthenticated OAuth callback proves authenticity by verifying it
(the browser redirect from Intuit cannot carry our bearer token).
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta

import jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.settings import Settings
from app.models.oauth_credential import OAuthCredential, OAuthProvider
from app.services.settings.service import SettingsService

log = logging.getLogger(__name__)

ACCOUNTING_SCOPE = "com.intuit.quickbooks.accounting"
DEFAULT_ACCESS_TTL_SECONDS = 3600  # Phase-0 verified
DEFAULT_REFRESH_TTL_SECONDS = 8_640_000  # 100 days, Phase-0 verified
# Refresh the access token this long before it actually expires.
ACCESS_REFRESH_LEEWAY = timedelta(minutes=5)

_STATE_PURPOSE = "qbo_oauth_connect"
_STATE_TTL_SECONDS = 600

# Token-health states surfaced to admin (never includes token values).
HEALTH_OK = "ok"
HEALTH_ACCESS_EXPIRED = "access_expired"  # refreshable
HEALTH_RECONNECT_REQUIRED = "reconnect_required"  # refresh chain dead


class QuickBooksConfigError(RuntimeError):
    """QBO OAuth env config (client id/secret/redirect) is missing."""


class QuickBooksOAuthError(RuntimeError):
    """An Intuit OAuth call failed (exchange/refresh/revoke)."""


class QuickBooksNotConnectedError(RuntimeError):
    """No stored credential — the integration isn't connected."""


# --------------------------------------------------------------------------- #
# Config + state
# --------------------------------------------------------------------------- #
def require_config(settings: Settings) -> None:
    """Raise if the QBO OAuth app credentials aren't configured."""
    missing = [
        name
        for name, value in (
            ("QBO_CLIENT_ID", settings.qbo_client_id),
            ("QBO_CLIENT_SECRET", settings.qbo_client_secret),
            ("QBO_REDIRECT_URI", settings.qbo_redirect_uri),
        )
        if not value
    ]
    if missing:
        raise QuickBooksConfigError("QuickBooks is not configured; set " + ", ".join(missing))


def issue_state(settings: Settings, *, actor_user_id: uuid.UUID) -> str:
    """Sign a short-lived CSRF state carrying the initiating user id."""
    now = int(datetime.now(UTC).timestamp())
    payload = {
        "purpose": _STATE_PURPOSE,
        "uid": str(actor_user_id),
        "iat": now,
        "exp": now + _STATE_TTL_SECONDS,
        "nonce": uuid.uuid4().hex,
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm="HS256")


def verify_state(settings: Settings, state: str) -> uuid.UUID:
    """Verify the CSRF state and return the initiating user id."""
    try:
        payload = jwt.decode(state, settings.jwt_secret_key, algorithms=["HS256"])
    except jwt.PyJWTError as exc:
        raise QuickBooksOAuthError("invalid or expired OAuth state") from exc
    if payload.get("purpose") != _STATE_PURPOSE:
        raise QuickBooksOAuthError("invalid OAuth state")
    try:
        return uuid.UUID(str(payload["uid"]))
    except (KeyError, ValueError) as exc:
        raise QuickBooksOAuthError("invalid OAuth state") from exc


# --------------------------------------------------------------------------- #
# intuitlib seams (monkeypatched in tests)
# --------------------------------------------------------------------------- #
def _build_auth_client(
    settings: Settings,
    *,
    realm_id: str | None = None,
    access_token: str | None = None,
    refresh_token: str | None = None,
):  # pragma: no cover - thin wrapper, exercised via monkeypatch in tests
    """Construct an intuitlib ``AuthClient`` (lazy import)."""
    from intuitlib.client import AuthClient

    require_config(settings)
    return AuthClient(
        client_id=settings.qbo_client_id,
        client_secret=settings.qbo_client_secret,
        environment=settings.qbo_environment,
        redirect_uri=settings.qbo_redirect_uri,
        realm_id=realm_id,
        access_token=access_token,
        refresh_token=refresh_token,
    )


def build_authorization_url(settings: Settings, *, state: str) -> str:
    """Build the Intuit consent URL for the accounting scope."""
    from intuitlib.enums import Scopes  # pragma: no cover - lazy import

    client = _build_auth_client(settings)
    return client.get_authorization_url([Scopes.ACCOUNTING], state_token=state)


# --------------------------------------------------------------------------- #
# Persistence
# --------------------------------------------------------------------------- #
async def get_credential(session: AsyncSession) -> OAuthCredential | None:
    """Return the stored QBO credential, or ``None`` if not connected."""
    stmt = select(OAuthCredential).where(OAuthCredential.provider == OAuthProvider.QUICKBOOKS.value)
    return (await session.execute(stmt)).scalar_one_or_none()


def _expiry(seconds: int | None, default: int, *, now: datetime) -> datetime:
    return now + timedelta(seconds=int(seconds) if seconds else default)


def _as_utc(value: datetime) -> datetime:
    """Treat a stored timestamp as UTC. SQLite drops tzinfo on read; Postgres
    keeps it. Coercing naive→UTC keeps comparisons correct on both."""
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


async def complete_authorization(
    session: AsyncSession,
    settings: Settings,
    *,
    code: str,
    realm_id: str,
    actor_user_id: uuid.UUID,
) -> OAuthCredential:
    """Exchange an auth code for tokens, persist them, mirror the realm id."""
    client = _build_auth_client(settings, realm_id=realm_id)
    try:
        client.get_bearer_token(code, realm_id=realm_id)
    except Exception as exc:  # intuitlib raises AuthClientError; keep broad
        raise QuickBooksOAuthError(f"token exchange failed: {exc}") from exc

    resolved_realm = realm_id or getattr(client, "realm_id", None)
    if not resolved_realm:
        raise QuickBooksOAuthError("Intuit callback did not include a realmId")

    now = datetime.now(UTC)
    cred = await get_credential(session)
    if cred is None:
        cred = OAuthCredential(provider=OAuthProvider.QUICKBOOKS.value, realm_id=resolved_realm)
        session.add(cred)
    cred.realm_id = resolved_realm
    cred.access_token = client.access_token
    cred.refresh_token = client.refresh_token
    cred.access_token_expires_at = _expiry(
        getattr(client, "expires_in", None), DEFAULT_ACCESS_TTL_SECONDS, now=now
    )
    cred.refresh_token_expires_at = _expiry(
        getattr(client, "x_refresh_token_expires_in", None),
        DEFAULT_REFRESH_TTL_SECONDS,
        now=now,
    )
    cred.scope = ACCOUNTING_SCOPE
    await session.flush()

    await SettingsService.set(
        "quickbooks.realm_id", resolved_realm, session=session, actor_user_id=actor_user_id
    )
    return cred


async def refresh_tokens(
    session: AsyncSession, settings: Settings, credential: OAuthCredential
) -> OAuthCredential:
    """Refresh the access token, persisting the (possibly rotated) refresh token."""
    client = _build_auth_client(
        settings,
        realm_id=credential.realm_id,
        access_token=credential.access_token,
        refresh_token=credential.refresh_token,
    )
    try:
        client.refresh(refresh_token=credential.refresh_token)
    except Exception as exc:
        raise QuickBooksOAuthError(f"token refresh failed; reconnect required: {exc}") from exc

    now = datetime.now(UTC)
    credential.access_token = client.access_token
    # Phase-0: the refresh token rotates — always store the latest value.
    credential.refresh_token = client.refresh_token
    credential.access_token_expires_at = _expiry(
        getattr(client, "expires_in", None), DEFAULT_ACCESS_TTL_SECONDS, now=now
    )
    rolling = getattr(client, "x_refresh_token_expires_in", None)
    if rolling:
        credential.refresh_token_expires_at = _expiry(rolling, DEFAULT_REFRESH_TTL_SECONDS, now=now)
    await session.flush()
    return credential


async def ensure_fresh_access_token(session: AsyncSession, settings: Settings) -> OAuthCredential:
    """Return a credential whose access token is valid, refreshing if needed.

    Used by later phases before making QBO API calls. Raises
    :class:`QuickBooksNotConnectedError` if not connected.
    """
    cred = await get_credential(session)
    if cred is None:
        raise QuickBooksNotConnectedError("QuickBooks is not connected")
    if datetime.now(UTC) >= _as_utc(cred.access_token_expires_at) - ACCESS_REFRESH_LEEWAY:
        cred = await refresh_tokens(session, settings, cred)
    return cred


async def disconnect(
    session: AsyncSession, settings: Settings, *, actor_user_id: uuid.UUID
) -> bool:
    """Revoke at Intuit (best-effort), delete the credential, clear settings.

    Idempotent: clears ``quickbooks.enabled``/``quickbooks.realm_id`` even when
    nothing was stored. Returns True if a credential was deleted.
    """
    cred = await get_credential(session)
    deleted = False
    if cred is not None:
        try:
            client = _build_auth_client(
                settings,
                realm_id=cred.realm_id,
                access_token=cred.access_token,
                refresh_token=cred.refresh_token,
            )
            client.revoke(token=cred.refresh_token)
        except Exception:  # revoke is best-effort; never block local cleanup
            log.warning("qbo token revoke failed; deleting local credential anyway", exc_info=True)
        await session.delete(cred)
        deleted = True

    await SettingsService.set(
        "quickbooks.enabled", False, session=session, actor_user_id=actor_user_id
    )
    await SettingsService.set(
        "quickbooks.realm_id", None, session=session, actor_user_id=actor_user_id
    )
    return deleted


def token_health(credential: OAuthCredential, *, now: datetime | None = None) -> str:
    """Classify a credential's token health (no secrets)."""
    now = now or datetime.now(UTC)
    if now >= _as_utc(credential.refresh_token_expires_at):
        return HEALTH_RECONNECT_REQUIRED
    if now >= _as_utc(credential.access_token_expires_at):
        return HEALTH_ACCESS_EXPIRED
    return HEALTH_OK
