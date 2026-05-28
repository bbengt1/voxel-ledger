"""Tests for the internal UPC-A generator service + endpoint."""

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


def test_build_internal_upc_a_format_and_checksum() -> None:
    upc = upc_service.build_internal_upc_a(1)
    assert upc.startswith(upc_service.INTERNAL_UPC_PREFIX)
    assert len(upc) == 12
    assert upc.isdigit()
    assert upc[2:11] == "000000001"
    assert upc_service.compute_check_digit(upc[:11]) == upc[11]


def test_build_internal_upc_a_rejects_out_of_range() -> None:
    with pytest.raises(ValueError):
        upc_service.build_internal_upc_a(0)
    with pytest.raises(ValueError):
        upc_service.build_internal_upc_a(10**9)


def test_is_valid_upc_a() -> None:
    assert upc_service.is_valid_upc_a("036000291452")
    assert not upc_service.is_valid_upc_a("036000291451")
    assert not upc_service.is_valid_upc_a("12345")
    assert not upc_service.is_valid_upc_a("abcdefghijkl")


# ---------------------------------------------------------------------------
# Allocator
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_allocate_unique_upc_starts_at_serial_one(
    session: AsyncSession,
) -> None:
    """Empty table → first issued serial is 1."""
    upc = await upc_service.allocate_unique_upc(session)
    assert upc == upc_service.build_internal_upc_a(1)


@pytest.mark.asyncio
async def test_allocate_unique_upc_uses_max_plus_one(
    session: AsyncSession,
) -> None:
    """Existing 04-prefixed UPCs at serials 1 and 5 → next is 6 (MAX+1)."""
    for serial in (1, 5):
        session.add(
            Product(
                sku=f"PROD-{serial:04d}",
                upc=upc_service.build_internal_upc_a(serial),
                name=f"p{serial}",
                unit_price=Decimal("1.00"),
            )
        )
    await session.commit()

    upc = await upc_service.allocate_unique_upc(session)
    assert upc == upc_service.build_internal_upc_a(6)


@pytest.mark.asyncio
async def test_allocate_unique_upc_ignores_non_internal_upcs(
    session: AsyncSession,
) -> None:
    """UPCs outside the 04 namespace must not affect the serial counter."""
    session.add(
        Product(
            sku="PROD-EXT",
            upc="123456789012",
            name="external",
            unit_price=Decimal("1.00"),
        )
    )
    await session.commit()

    upc = await upc_service.allocate_unique_upc(session)
    assert upc == upc_service.build_internal_upc_a(1)


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_upc_endpoint_returns_valid_internal_upc(
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
    assert upc.startswith(upc_service.INTERNAL_UPC_PREFIX)
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
