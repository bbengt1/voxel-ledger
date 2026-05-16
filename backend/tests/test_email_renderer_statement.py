"""Statement renderer test (Phase 7.7, #115)."""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from app.models import Base
from app.models.auth import Role, User
from app.services import customers as customers_service
from app.services.email.renderers import statement as statement_renderer
from sqlalchemy.ext.asyncio import AsyncSession


@pytest_asyncio.fixture
async def schema(engine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


@pytest_asyncio.fixture
async def actor(session: AsyncSession, schema: None) -> User:
    user = User(
        id=uuid.uuid4(),
        email="owner@example.com",
        full_name="Owner",
        password_hash="x",
        role=Role.OWNER,
        is_active=True,
    )
    session.add(user)
    await session.commit()
    return user


@pytest.mark.asyncio
async def test_statement_render_with_no_invoices(session: AsyncSession, actor: User) -> None:
    customer = await customers_service.create(
        session,
        display_name="Acme",
        primary_email="acme@example.com",
        actor_user_id=actor.id,
    )
    await session.commit()
    rendered = await statement_renderer.render(customer.id, session=session)
    assert "Acme" in rendered.subject
    assert "Acme" in rendered.body_html
    assert rendered.body_text is not None
    assert "Total outstanding" in rendered.body_text
