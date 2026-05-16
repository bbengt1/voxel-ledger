"""Stub carrier deterministic-tracking behavior (Phase 6.6, #98)."""

from __future__ import annotations

from decimal import Decimal

from app.services.shipping import carriers


def test_stub_carrier_returns_test_prefixed_tracking_and_fixed_cost() -> None:
    client = carriers.StubCarrier()
    result = client.purchase_label(
        ship_from={"name": "Shop", "street1": "1 Shop Way"},
        ship_to={"name": "Cust", "street1": "2 Cust Way"},
        weight_grams=250,
        dimensions_cm={"l": 10, "w": 10, "h": 5},
        service_level="priority",
    )
    assert result.tracking_number is not None
    assert result.tracking_number.startswith("TEST-")
    # ``TEST-{uuid}`` => 5 + 36 chars.
    assert len(result.tracking_number) == 5 + 36
    assert result.cost_amount == Decimal("9.99")
    assert result.carrier == "stub"
    assert result.pdf_bytes.startswith(b"%PDF-")


def test_stub_carrier_get_tracking_reports_in_transit() -> None:
    client = carriers.StubCarrier()
    tracking = client.get_tracking("TEST-anything")
    assert tracking.status == "in_transit"


def test_factory_returns_stub_when_requested() -> None:
    client = carriers.get_carrier_client("stub")
    assert isinstance(client, carriers.StubCarrier)


def test_factory_falls_back_to_static_for_unknown_carrier_slugs() -> None:
    # USPS / UPS / FedEx have no real client yet — the factory should
    # silently fall back to the static carrier so the operator at
    # least gets a printable label.
    for slug in ("usps", "ups", "fedex", ""):
        client = carriers.get_carrier_client(slug)
        assert isinstance(client, carriers.StaticFallbackCarrier), slug


def test_factory_returns_static_for_none() -> None:
    client = carriers.get_carrier_client(None)
    assert isinstance(client, carriers.StaticFallbackCarrier)
