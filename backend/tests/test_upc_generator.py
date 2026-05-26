"""Tests for the UPC-A generator service + endpoint."""

from __future__ import annotations

from decimal import Decimal

import pytest
import pytest_asyncio
from app.models import Base
from app.models.auth import Role
from app.models.product import Product
from app.services import upc as upc_service
from app.services.auth import create_user
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


@pytest_asyncio.fixture(autouse=True)
async def _create_schema(engine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def _token_for(role: Role, client: AsyncClient, session: AsyncSession) -> str:
    email = f"{role.value}@example.com"
    await create_user(
        session,
        email=email,
        password="pw-correct",
        full_name=role.value,
        role=role,
        bcrypt_rounds=4,
    )
    await session.commit()
    r = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "pw-correct"},
    )
    return r.json()["access_token"]


# ---------------------------------------------------------------------------
# Pure functions
# ---------------------------------------------------------------------------


def test_check_digit_known_value() -> None:
    """GS1 reference: ``03600029145`` → check digit ``2`` → UPC ``036000291452``."""
    assert upc_service.compute_check_digit("03600029145") == "2"


def test_check_digit_all_zeros() -> None:
    assert upc_service.compute_check_digit("00000000000") == "0"


def test_check_digit_rejects_non_11_digit_input() -> None:
    with pytest.raises(ValueError):
        upc_service.compute_check_digit("12345")
    with pytest.raises(ValueError):
        upc_service.compute_check_digit("abcdefghijk")


def test_generate_upc_a_returns_12_digits_with_valid_checksum() -> None:
    for _ in range(50):
        upc = upc_service.generate_upc_a()
        assert len(upc) == 12
        assert upc.isdigit()
        # Recomputing the check digit on the first 11 must yield the 12th.
        assert upc_service.compute_check_digit(upc[:11]) == upc[11]


# ---------------------------------------------------------------------------
# Allocator
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_allocate_unique_upc_avoids_existing_value(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When the first candidate collides, the allocator retries."""
    session.add(
        Product(
            sku="PROD-2026-0001",
            upc="123456789012",
            name="taken",
            unit_price=Decimal("1.00"),
        )
    )
    await session.commit()

    candidates = iter(["123456789012", "999999999993"])
    monkeypatch.setattr(upc_service, "generate_upc_a", lambda: next(candidates))

    allocated = await upc_service.allocate_unique_upc(session)
    assert allocated == "999999999993"


@pytest.mark.asyncio
async def test_allocate_unique_upc_raises_when_attempts_exhausted(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    session.add(
        Product(
            sku="PROD-2026-0001",
            upc="111111111117",
            name="taken",
            unit_price=Decimal("1.00"),
        )
    )
    await session.commit()

    monkeypatch.setattr(upc_service, "generate_upc_a", lambda: "111111111117")

    with pytest.raises(upc_service.UpcGenerationError):
        await upc_service.allocate_unique_upc(session, max_attempts=3)


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_upc_endpoint_returns_valid_upc(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    token = await _token_for(Role.OWNER, client, app_session)
    response = await client.post(
        "/api/v1/products/upc/generate",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    upc = payload["upc"]
    assert len(upc) == 12
    assert upc.isdigit()
    assert upc_service.compute_check_digit(upc[:11]) == upc[11]


@pytest.mark.asyncio
async def test_generate_upc_endpoint_forbidden_for_viewer(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    token = await _token_for(Role.VIEWER, client, app_session)
    response = await client.post(
        "/api/v1/products/upc/generate",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403
