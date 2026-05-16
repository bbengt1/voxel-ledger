"""Quote renderer test (Phase 7.7, #115)."""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
import pytest_asyncio
from app.models import Base
from app.models.auth import Role, User
from app.services import customers as customers_service
from app.services import quotes as quotes_service
from app.services.email.renderers import quote as quote_renderer
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
async def test_quote_render_returns_subject_and_attachment(
    session: AsyncSession, actor: User
) -> None:
    customer = await customers_service.create(
        session,
        display_name="Acme",
        primary_email="acme@example.com",
        actor_user_id=actor.id,
    )
    await session.commit()
    quote = await quotes_service.create_draft(
        session,
        customer_id=customer.id,
        actor_user_id=actor.id,
        items=[
            {
                "kind": "manual",
                "description": "Widget",
                "quantity": Decimal("1"),
                "unit_price": Decimal("10"),
            }
        ],
    )
    await session.commit()

    rendered = await quote_renderer.render(quote.id, session=session)
    assert rendered.subject.startswith("Quote ")
    assert "Acme" in rendered.body_html
    assert "10" in rendered.body_html
    assert len(rendered.attachments) == 1
    att = rendered.attachments[0]
    assert att.filename.endswith(".pdf")
    assert att.content.startswith(b"%PDF")
