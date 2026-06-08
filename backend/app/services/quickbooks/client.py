"""Thin QuickBooks Online REST client (#315; hardened in Phase 3 #316).

A minimal authenticated wrapper over the QBO v3 Accounting API used by the
master-data and account-map services. It handles: base-URL selection
(sandbox/production), bearer auth via the Phase-1 token refresh, the pinned
``minorversion`` (Phase-0: 75), the ``requestid`` idempotency key on creates
(Phase-0 canonical strategy), and SQL-style queries.

Phase 3 (#316) extends this same chokepoint with the concurrency / rate-limit
guard (≤10 concurrent, 500/min), 429 backoff, and the batch endpoint. Kept
deliberately small here so Phase-2 callers (admin-triggered upserts) work today.
"""

from __future__ import annotations

import uuid
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.settings import Settings
from app.services.quickbooks import oauth

MINOR_VERSION = "75"  # Phase-0 verified latest; 1-74 deprecated 2025-08-01.
_TIMEOUT_SECONDS = 30.0

_PROD_BASE = "https://quickbooks.api.intuit.com"
_SANDBOX_BASE = "https://sandbox-quickbooks.api.intuit.com"


class QuickBooksApiError(RuntimeError):
    """A QBO API call returned a non-success status."""

    def __init__(self, status_code: int, message: str) -> None:
        self.status_code = status_code
        super().__init__(f"QBO API {status_code}: {message}")


def base_url(settings: Settings) -> str:
    return _PROD_BASE if settings.qbo_environment == "production" else _SANDBOX_BASE


class QuickBooksClient:
    """Authenticated QBO v3 client bound to a session + settings."""

    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self._session = session
        self._settings = settings

    async def _auth(self) -> tuple[str, str]:
        """Return (realm_id, access_token), refreshing the token if needed."""
        cred = await oauth.ensure_fresh_access_token(self._session, self._settings)
        return cred.realm_id, cred.access_token

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str] | None = None,
        json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        realm_id, access_token = await self._auth()
        url = f"{base_url(self._settings)}/v3/company/{realm_id}/{path}"
        query = {"minorversion": MINOR_VERSION, **(params or {})}
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as http:
                resp = await http.request(method, url, params=query, json=json, headers=headers)
        except httpx.HTTPError as exc:
            raise QuickBooksApiError(0, f"transport error: {exc}") from exc
        if resp.status_code >= 400:
            raise QuickBooksApiError(resp.status_code, (resp.text or "")[:512])
        return resp.json() if resp.content else {}

    async def query(self, statement: str, entity: str) -> list[dict[str, Any]]:
        """Run a QBO SQL-style query and return the rows for ``entity``.

        ``entity`` is the PascalCase response key (e.g. "Customer", "Account").
        """
        body = await self._request("GET", "query", params={"query": statement})
        return body.get("QueryResponse", {}).get(entity, [])

    async def create(
        self, entity: str, payload: dict[str, Any], *, request_id: str | None = None
    ) -> dict[str, Any]:
        """Create a QBO entity. ``entity`` is PascalCase ("Customer"); a
        ``requestid`` is sent for idempotency (Phase-0)."""
        params = {"requestid": request_id or uuid.uuid4().hex}
        body = await self._request("POST", entity.lower(), params=params, json=payload)
        return body.get(entity, {})

    async def update(self, entity: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Sparse-update a QBO entity. ``payload`` must carry ``Id``,
        ``SyncToken`` and ``sparse: true``."""
        body = await self._request("POST", entity.lower(), json=payload)
        return body.get(entity, {})

    async def read(self, entity: str, qbo_id: str) -> dict[str, Any]:
        body = await self._request("GET", f"{entity.lower()}/{qbo_id}")
        return body.get(entity, {})
