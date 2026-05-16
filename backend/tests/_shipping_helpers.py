"""Shared helpers for shipping tests (Phase 6.6, #98)."""

from __future__ import annotations

import tempfile
import uuid
from datetime import UTC, datetime
from decimal import Decimal

from app.services import sales as sales_service
from app.services.settings.service import SettingsService
from sqlalchemy.ext.asyncio import AsyncSession

from tests._sales_helpers import seed_channel, seed_user

SHIP_TO_FIXTURE: dict[str, object] = {
    "name": "Test Customer",
    "street1": "123 Main St",
    "city": "Anytown",
    "region": "CA",
    "postal_code": "94000",
    "country": "US",
}

SHIP_FROM_FIXTURE: dict[str, object] = {
    "name": "Voxel Ledger Shop",
    "street1": "1 Shop Way",
    "city": "Workshop",
    "region": "WA",
    "postal_code": "98000",
    "country": "US",
}


async def seed_shipping_settings(session: AsyncSession) -> str:
    """Configure ``shipping.*`` settings with values fit for tests.

    Returns the on-disk path used for label storage so the caller can
    inspect / clean it up if it cares.
    """
    tmp_root = tempfile.mkdtemp(prefix="shipping-labels-")
    await SettingsService.set(
        "shipping.labels_storage_root",
        tmp_root,
        session=session,
        actor_user_id=None,
    )
    await SettingsService.set(
        "shipping.ship_from_address",
        SHIP_FROM_FIXTURE,
        session=session,
        actor_user_id=None,
    )
    # Leave default carrier at "static_fallback" — tests that want the
    # stub pass it in directly via ``purchase_label(carrier_client=...)``
    # so settings don't have to be churned per-test.
    await session.commit()
    return tmp_root


async def seed_draft_sale(session: AsyncSession):
    """Create a tiny manual-line sale wired against a fresh channel.

    Returns the ``Sale`` row. Confirming the sale is not needed for
    shipment tests since the spec doesn't require ``sale.state ==
    confirmed`` before a shipment can be created.
    """
    user = await seed_user(session, email=f"owner-{uuid.uuid4().hex}@example.com")
    channel = await seed_channel(
        session,
        name=f"chan-{uuid.uuid4().hex[:6]}",
        slug=f"chan-{uuid.uuid4().hex[:6]}",
        fee_percent="0.00",
    )
    sale = await sales_service.create_draft(
        session,
        channel_id=channel.id,
        external_order_id=None,
        customer_name="Test Customer",
        customer_email="x@example.com",
        occurred_at=datetime.now(UTC),
        discount_amount=Decimal("0"),
        shipping_amount=Decimal("0"),
        tax_amount=Decimal("0"),
        notes=None,
        items=[
            {
                "kind": "manual",
                "description": "thing",
                "quantity": "1",
                "unit_price": "10",
            }
        ],
        actor_user_id=user.id,
    )
    await session.commit()
    return sale


__all__ = [
    "SHIP_FROM_FIXTURE",
    "SHIP_TO_FIXTURE",
    "seed_draft_sale",
    "seed_shipping_settings",
]
