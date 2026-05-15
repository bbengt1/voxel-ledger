"""Missing sales-posting defaults raise a clear error (Phase 6.3, #95)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from app.services import sales as sales_service
from app.services.cogs.service import MissingSalesPostingAccountError
from sqlalchemy.ext.asyncio import AsyncSession

from tests._sales_helpers import seed_channel, seed_user


@pytest.mark.asyncio
async def test_confirm_raises_when_cogs_account_unset(
    app_session: AsyncSession,
) -> None:
    """No ``sales_posting.*`` settings configured → clear error.

    The error message must contain ``"configure default sales-posting accounts"``
    so the router's 400 response is unambiguous for operators.
    """
    user = await seed_user(app_session)
    channel = await seed_channel(app_session, fee_model="none", fee_percent=None)
    sale = await sales_service.create_draft(
        app_session,
        channel_id=channel.id,
        external_order_id=None,
        customer_name="C",
        customer_email=None,
        occurred_at=datetime.now(UTC),
        items=[
            {
                "kind": "manual",
                "description": "Line",
                "quantity": "1",
                "unit_price": "10.00",
            }
        ],
        actor_user_id=user.id,
    )
    await app_session.commit()

    with pytest.raises(MissingSalesPostingAccountError) as exc_info:
        await sales_service.confirm(app_session, sale_id=sale.id, actor_user_id=user.id)
    assert "configure default sales-posting accounts" in str(exc_info.value)
