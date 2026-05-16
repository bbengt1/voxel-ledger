"""Quote convert-to-invoice stub (Phase 7.2, #110).

The real implementation depends on the Phase 7.3 (#111) invoice service.
Until that lands, the endpoint must return HTTP 501 with the documented
body so callers can feature-detect cleanly::

    {"detail": "Requires Phase 7.3 invoices", "phase": "7.3"}

The seam (column + state machine) is in place so the swap to the real
implementation in #111 is small.
"""

from __future__ import annotations

import pytest
from app.models.auth import Role
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests._quotes_helpers import auth_header, sample_quote_body, seed_customer, token_for


@pytest.mark.asyncio
async def test_convert_returns_501_with_documented_body(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    customer = await seed_customer(app_session)
    owner = await token_for(Role.OWNER, client, app_session)
    create = await client.post(
        "/api/v1/quotes",
        headers=auth_header(owner),
        json=sample_quote_body(customer_id=str(customer.id)),
    )
    quote_id = create.json()["id"]
    await client.post(f"/api/v1/quotes/{quote_id}/send", headers=auth_header(owner))
    await client.post(f"/api/v1/quotes/{quote_id}/accept", headers=auth_header(owner))

    r = await client.post(
        f"/api/v1/quotes/{quote_id}/convert-to-invoice",
        headers=auth_header(owner),
    )
    assert r.status_code == 501, r.text
    body = r.json()
    # FastAPI wraps the dict ``detail`` under the outer "detail" key.
    inner = body.get("detail")
    assert isinstance(inner, dict), body
    assert inner.get("detail") == "Requires Phase 7.3 invoices"
    assert inner.get("phase") == "7.3"


@pytest.mark.asyncio
async def test_convert_unknown_quote_returns_404(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    owner = await token_for(Role.OWNER, client, app_session)
    r = await client.post(
        "/api/v1/quotes/00000000-0000-0000-0000-000000000000/convert-to-invoice",
        headers=auth_header(owner),
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_convert_requires_write_role(client: AsyncClient, app_session: AsyncSession) -> None:
    customer = await seed_customer(app_session)
    owner = await token_for(Role.OWNER, client, app_session)
    create = await client.post(
        "/api/v1/quotes",
        headers=auth_header(owner),
        json=sample_quote_body(customer_id=str(customer.id)),
    )
    quote_id = create.json()["id"]
    viewer = await token_for(Role.VIEWER, client, app_session)
    r = await client.post(
        f"/api/v1/quotes/{quote_id}/convert-to-invoice",
        headers=auth_header(viewer),
    )
    assert r.status_code == 403
