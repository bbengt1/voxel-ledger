"""Quote totals math: discount + tax, NO channel fee or shipping (Phase 7.2, #110).

Quotes don't have a sales channel and don't ship — totals math is:

    extended_amount = quantity * unit_price
    subtotal        = sum(extended_amount)
    total_amount    = subtotal - discount_amount + tax_amount
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from app.services import quotes as quotes_service
from sqlalchemy.ext.asyncio import AsyncSession

from tests._quotes_helpers import seed_customer, seed_user


def _items(*pairs: tuple[str, str]) -> list[dict]:
    return [
        {
            "kind": "manual",
            "description": f"Line {idx}",
            "quantity": qty,
            "unit_price": price,
        }
        for idx, (qty, price) in enumerate(pairs, start=1)
    ]


def _D(x) -> Decimal:
    return x if isinstance(x, Decimal) else Decimal(x)


@pytest.mark.asyncio
async def test_basic_subtotal(app_session: AsyncSession) -> None:
    user = await seed_user(app_session)
    customer = await seed_customer(app_session)
    quote = await quotes_service.create_draft(
        app_session,
        customer_id=customer.id,
        items=_items(("2", "10"), ("1", "5.5")),
        actor_user_id=user.id,
    )
    await app_session.commit()
    assert _D(quote.subtotal) == Decimal("25.500000")
    assert _D(quote.total_amount) == Decimal("25.500000")


@pytest.mark.asyncio
async def test_total_includes_discount_and_tax(app_session: AsyncSession) -> None:
    user = await seed_user(app_session)
    customer = await seed_customer(app_session)
    quote = await quotes_service.create_draft(
        app_session,
        customer_id=customer.id,
        discount_amount=Decimal("5"),
        tax_amount=Decimal("2"),
        items=_items(("1", "100")),
        actor_user_id=user.id,
    )
    await app_session.commit()
    # subtotal=100, discount=5, tax=2 -> total = 100 - 5 + 2 = 97
    assert _D(quote.subtotal) == Decimal("100.000000")
    assert _D(quote.discount_amount) == Decimal("5.000000")
    assert _D(quote.tax_amount) == Decimal("2.000000")
    assert _D(quote.total_amount) == Decimal("97.000000")


@pytest.mark.asyncio
async def test_no_channel_fee_field(app_session: AsyncSession) -> None:
    """Quotes don't have channel_fee_amount — verify the model lacks it."""
    user = await seed_user(app_session)
    customer = await seed_customer(app_session)
    quote = await quotes_service.create_draft(
        app_session,
        customer_id=customer.id,
        items=_items(("1", "10")),
        actor_user_id=user.id,
    )
    await app_session.commit()
    assert not hasattr(quote, "channel_fee_amount")
    assert not hasattr(quote, "shipping_amount")


@pytest.mark.asyncio
async def test_line_precision_six_dp(app_session: AsyncSession) -> None:
    user = await seed_user(app_session)
    customer = await seed_customer(app_session)
    quote = await quotes_service.create_draft(
        app_session,
        customer_id=customer.id,
        items=_items(("0.333333", "1.000001")),
        actor_user_id=user.id,
    )
    await app_session.commit()
    # 0.333333 * 1.000001 = 0.333333333333; quantized to 6dp -> 0.333333
    assert _D(quote.items[0].extended_amount) == Decimal("0.333333")


@pytest.mark.asyncio
async def test_update_replays_totals(app_session: AsyncSession) -> None:
    user = await seed_user(app_session)
    customer = await seed_customer(app_session)
    quote = await quotes_service.create_draft(
        app_session,
        customer_id=customer.id,
        items=_items(("1", "10")),
        actor_user_id=user.id,
    )
    await app_session.commit()

    await quotes_service.update_draft(
        app_session,
        quote_id=quote.id,
        patch={
            "items": [{"kind": "manual", "description": "Y", "quantity": "5", "unit_price": "4"}],
            "tax_amount": "1",
        },
        actor_user_id=user.id,
    )
    await app_session.commit()
    quote = await quotes_service.get(app_session, quote.id)
    # subtotal = 20, total = 20 - 0 + 1 = 21
    assert _D(quote.subtotal) == Decimal("20.000000")
    assert _D(quote.total_amount) == Decimal("21.000000")
