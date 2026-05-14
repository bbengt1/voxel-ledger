"""@require_role: every role x every gate combination."""

from __future__ import annotations

import pytest
import pytest_asyncio
from app.api.deps import require_role
from app.core import db as db_module
from app.core.settings import Settings
from app.main import create_app
from app.models import Base
from app.models.auth import Role
from app.services.auth import create_user
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient


def _make_endpoint(role: Role):
    gate = Depends(require_role(role))

    async def endpoint(_user=gate) -> dict[str, str]:
        return {"ok": "true"}

    return endpoint


def _build_app(settings: Settings) -> FastAPI:
    app = create_app(settings=settings)
    for role in Role:
        app.add_api_route(
            f"/test-gate/{role.value}",
            _make_endpoint(role),
            methods=["GET"],
            name=f"gate-{role.value}",
        )

    multi_gate = Depends(require_role(Role.OWNER, "bookkeeper"))

    async def multi_endpoint(_u=multi_gate) -> dict[str, str]:
        return {"ok": "true"}

    app.add_api_route("/test-gate/multi", multi_endpoint, methods=["GET"])
    return app


@pytest_asyncio.fixture
async def gated_client(settings: Settings):
    app = _build_app(settings)
    transport = ASGITransport(app=app)
    async with (
        AsyncClient(transport=transport, base_url="http://testserver") as ac,
        app.router.lifespan_context(app),
    ):
        engine = db_module.get_engine()
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        yield ac
    await db_module.dispose_engine()


@pytest_asyncio.fixture
async def gated_session(gated_client):
    factory = db_module._session_factory
    assert factory is not None
    async with factory() as s:
        yield s


async def _token_for(role: Role, client: AsyncClient, session) -> str:
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
    login = await client.post("/api/v1/auth/login", json={"email": email, "password": "pw-correct"})
    return login.json()["access_token"]


@pytest.mark.asyncio
@pytest.mark.parametrize("subject", list(Role))
@pytest.mark.parametrize("gate", list(Role))
async def test_role_matrix(
    gated_client: AsyncClient,
    gated_session,
    subject: Role,
    gate: Role,
) -> None:
    token = await _token_for(subject, gated_client, gated_session)
    r = await gated_client.get(
        f"/test-gate/{gate.value}",
        headers={"Authorization": f"Bearer {token}"},
    )
    expected = 200 if subject == gate else 403
    assert r.status_code == expected, (subject, gate, r.text)


@pytest.mark.asyncio
async def test_multi_role_gate(gated_client: AsyncClient, gated_session) -> None:
    """A gate accepting multiple roles admits any of them."""
    for role, expected in [
        (Role.OWNER, 200),
        (Role.BOOKKEEPER, 200),
        (Role.PRODUCTION, 403),
        (Role.SALES, 403),
        (Role.VIEWER, 403),
    ]:
        token = await _token_for(role, gated_client, gated_session)
        r = await gated_client.get("/test-gate/multi", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == expected, (role, r.text)
