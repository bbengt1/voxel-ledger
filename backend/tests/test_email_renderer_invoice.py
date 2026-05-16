"""Invoice renderer test (Phase 7.7, #115)."""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
import pytest_asyncio
from app.models import Base
from app.models.auth import Role, User
from app.services import customers as customers_service
from app.services import invoices as invoices_service
from app.services.email.renderers import invoice as invoice_renderer
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
async def test_invoice_render_returns_subject_and_pdf(session: AsyncSession, actor: User) -> None:
    customer = await customers_service.create(
        session,
        display_name="Acme",
        primary_email="acme@example.com",
        actor_user_id=actor.id,
    )
    await session.commit()
    invoice = await invoices_service.create_draft(
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

    rendered = await invoice_renderer.render(invoice.id, session=session)
    assert "Invoice" in rendered.subject
    assert "Acme" in rendered.body_html
    assert len(rendered.attachments) == 1
    assert rendered.attachments[0].content.startswith(b"%PDF")
