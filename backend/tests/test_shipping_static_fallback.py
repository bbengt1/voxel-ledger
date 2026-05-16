"""Static-fallback carrier behavior (Phase 6.6, #98).

Asserts the three properties the spec calls out: the rendered PDF is
non-empty (i.e. a real PDF, not a stub placeholder), the tracking
number is null, and the cost is zero.
"""

from __future__ import annotations

from decimal import Decimal

from app.services.shipping import carriers
from app.services.shipping.service import purchase_label
from sqlalchemy.ext.asyncio import AsyncSession

from tests._shipping_helpers import (
    SHIP_TO_FIXTURE,
    seed_draft_sale,
    seed_shipping_settings,
)


def test_static_carrier_label_pdf_is_non_empty_with_no_tracking_and_zero_cost() -> None:
    """Direct unit check that doesn't touch the DB.

    The carrier client is pure-Python so we can exercise it without any
    session plumbing — gives us a fast failure signal if reportlab ever
    breaks.
    """
    client = carriers.StaticFallbackCarrier()
    result = client.purchase_label(
        ship_from={"name": "Shop", "street1": "1 Shop Way"},
        ship_to={"name": "Cust", "street1": "2 Cust Way"},
        weight_grams=250,
        dimensions_cm={"l": 10, "w": 10, "h": 5},
        service_level="ground",
    )
    assert isinstance(result.pdf_bytes, bytes)
    assert len(result.pdf_bytes) > 0
    # All real PDFs start with the ``%PDF-`` magic. If reportlab gives
    # us anything else we want a noisy failure.
    assert result.pdf_bytes.startswith(b"%PDF-")
    assert result.tracking_number is None
    assert result.tracking_url is None
    assert result.cost_amount == Decimal("0")
    assert result.carrier == "static_fallback"


async def test_purchase_label_through_service_persists_pdf_and_zero_cost(
    app_session: AsyncSession,
) -> None:
    """End-to-end through the service: the row's metadata matches the
    static-fallback invariants and the PDF is written under the
    expected storage key."""
    await seed_shipping_settings(app_session)
    sale = await seed_draft_sale(app_session)

    from app.services import shipping as shipping_service

    shipment = await shipping_service.create_shipment(
        sale.id,
        ship_to=SHIP_TO_FIXTURE,
        weight_grams=200,
        dimensions_cm={"l": 5, "w": 5, "h": 5},
        service_level="ground",
        carrier_hint="static_fallback",
        session=app_session,
    )
    await app_session.commit()

    shipment = await shipping_service.purchase_label(shipment.id, session=app_session)
    await app_session.commit()

    assert shipment.tracking_number is None
    assert shipment.cost_amount == Decimal("0")
    assert shipment.label_pdf_storage_key == f"shipping-labels/{shipment.id}.pdf"

    pdf_bytes = await shipping_service.load_label_pdf(shipment.id, session=app_session)
    assert pdf_bytes.startswith(b"%PDF-")
    assert len(pdf_bytes) > 100


__all__ = ["purchase_label"]  # quiet ruff: imported for re-export verification
