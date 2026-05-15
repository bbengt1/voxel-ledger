"""Sales totals math: discount, shipping, tax, channel-fee snapshot (Phase 6.2, #94)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from app.services import sales as sales_service
from sqlalchemy.ext.asyncio import AsyncSession

from tests._sales_helpers import seed_channel, seed_user


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


def _D(x: Decimal | str) -> Decimal:
    return x if isinstance(x, Decimal) else Decimal(x)


@pytest.mark.asyncio
async def test_basic_subtotal(app_session: AsyncSession) -> None:
    user = await seed_user(app_session)
    channel = await seed_channel(app_session, fee_model="none", fee_percent=None)
    sale = await sales_service.create_draft(
        app_session,
        channel_id=channel.id,
        external_order_id=None,
        customer_name="X",
        customer_email=None,
        occurred_at=datetime.now(UTC),
        items=_items(("2", "10"), ("1", "5.5")),
        actor_user_id=user.id,
    )
    await app_session.commit()
    # 2 * 10 + 1 * 5.5 = 25.5
    assert _D(sale.subtotal) == Decimal("25.500000")
    assert _D(sale.total_amount) == Decimal("25.500000")
    assert _D(sale.channel_fee_amount) == Decimal("0.000000")


@pytest.mark.asyncio
async def test_total_includes_shipping_and_tax_excludes_fee(app_session: AsyncSession) -> None:
    user = await seed_user(app_session)
    channel = await seed_channel(
        app_session, fee_model="percent_plus_flat", fee_percent="0.029", fee_flat="0.30"
    )
    sale = await sales_service.create_draft(
        app_session,
        channel_id=channel.id,
        external_order_id=None,
        customer_name="X",
        customer_email=None,
        occurred_at=datetime.now(UTC),
        discount_amount=Decimal("5"),
        shipping_amount=Decimal("3"),
        tax_amount=Decimal("2"),
        items=_items(("1", "100")),
        actor_user_id=user.id,
    )
    await app_session.commit()
    # subtotal=100, discount=5, shipping=3, tax=2
    # total = 100 - 5 + 3 + 2 = 100
    assert _D(sale.subtotal) == Decimal("100.000000")
    assert _D(sale.total_amount) == Decimal("100.000000")
    # fee_gross = subtotal - discount + shipping = 100 - 5 + 3 = 98
    # fee = 98 * 0.029 + 0.30 = 2.842 + 0.30 = 3.142
    assert _D(sale.channel_fee_amount) == Decimal("3.142000")


@pytest.mark.asyncio
async def test_decimal_precision_holds(app_session: AsyncSession) -> None:
    """Fractional quantity * unit_price stays in Decimal (no float drift)."""
    user = await seed_user(app_session)
    channel = await seed_channel(app_session, fee_model="none", fee_percent=None)
    sale = await sales_service.create_draft(
        app_session,
        channel_id=channel.id,
        external_order_id=None,
        customer_name="X",
        customer_email=None,
        occurred_at=datetime.now(UTC),
        items=_items(("0.333333", "9.99")),
        actor_user_id=user.id,
    )
    await app_session.commit()
    # 0.333333 * 9.99 = 3.32999667
    # Quantized to 6dp = 3.329997
    assert _D(sale.subtotal) == Decimal("3.329997")


@pytest.mark.asyncio
async def test_channel_fee_snapshot_does_not_recompute_on_confirm(
    app_session: AsyncSession,
) -> None:
    """Confirming a sale must NOT recompute the channel fee (operator-side)."""
    user = await seed_user(app_session)
    channel = await seed_channel(
        app_session, fee_model="percent", fee_percent="0.05", fee_flat=None
    )
    sale = await sales_service.create_draft(
        app_session,
        channel_id=channel.id,
        external_order_id=None,
        customer_name="X",
        customer_email=None,
        occurred_at=datetime.now(UTC),
        items=_items(("1", "100")),
        actor_user_id=user.id,
    )
    await app_session.commit()
    original_fee = Decimal(sale.channel_fee_amount)
    assert original_fee == Decimal("5.000000")

    # Operator changes the channel's fee model AFTER the sale.
    from app.services import sales_channels as channels_service

    await channels_service.update(
        app_session,
        channel_id=channel.id,
        patch={"fee_percent": Decimal("0.20")},
        actor_user_id=None,
    )
    await app_session.commit()

    # Confirm — must NOT recompute fee.
    await sales_service.confirm(app_session, sale_id=sale.id, actor_user_id=None)
    await app_session.commit()

    confirmed = await sales_service.get(app_session, sale.id)
    assert _D(confirmed.channel_fee_amount) == original_fee


@pytest.mark.asyncio
async def test_update_recomputes_totals(app_session: AsyncSession) -> None:
    user = await seed_user(app_session)
    channel = await seed_channel(
        app_session, fee_model="percent", fee_percent="0.10", fee_flat=None
    )
    sale = await sales_service.create_draft(
        app_session,
        channel_id=channel.id,
        external_order_id=None,
        customer_name="X",
        customer_email=None,
        occurred_at=datetime.now(UTC),
        items=_items(("1", "10")),
        actor_user_id=user.id,
    )
    await app_session.commit()
    assert _D(sale.subtotal) == Decimal("10.000000")
    assert _D(sale.channel_fee_amount) == Decimal("1.000000")

    await sales_service.update_draft(
        app_session,
        sale_id=sale.id,
        patch={
            "items": [
                {
                    "kind": "manual",
                    "description": "Big",
                    "quantity": "1",
                    "unit_price": "200",
                }
            ]
        },
        actor_user_id=None,
    )
    await app_session.commit()
    updated = await sales_service.get(app_session, sale.id)
    assert _D(updated.subtotal) == Decimal("200.000000")
    assert _D(updated.channel_fee_amount) == Decimal("20.000000")
