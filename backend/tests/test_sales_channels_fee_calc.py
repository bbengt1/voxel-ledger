"""Pure-function tests for ``compute_fee`` across the fee matrix.

Decimal math, no DB, no clock. Anchored on the Phase 6.1 spec values
(e.g. Shopify-ish 2.9% + $0.30, Etsy-ish 6.5% transaction fee, free POS).
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from app.models.sales_channel import SalesChannel, SalesChannelFeeModel, SalesChannelKind
from app.services import sales_channels as channels_service


def _channel(
    fee_model: SalesChannelFeeModel,
    *,
    fee_percent: Decimal | None = None,
    fee_flat: Decimal | None = None,
) -> SalesChannel:
    return SalesChannel(
        name=f"test-{fee_model.value}",
        slug=fee_model.value,
        kind=SalesChannelKind.POS,
        fee_model=fee_model,
        fee_percent=fee_percent,
        fee_flat=fee_flat,
        is_active=True,
    )


def test_compute_fee_none_is_zero() -> None:
    ch = _channel(SalesChannelFeeModel.NONE)
    assert channels_service.compute_fee(ch, Decimal("125.00")) == Decimal("0.000000")


def test_compute_fee_flat_returns_flat() -> None:
    ch = _channel(SalesChannelFeeModel.FLAT, fee_flat=Decimal("0.30"))
    assert channels_service.compute_fee(ch, Decimal("125.00")) == Decimal("0.300000")


def test_compute_fee_percent() -> None:
    # 3.49 % of $125.00 = $4.3625
    ch = _channel(SalesChannelFeeModel.PERCENT, fee_percent=Decimal("0.0349"))
    assert channels_service.compute_fee(ch, Decimal("125.00")) == Decimal("4.362500")


def test_compute_fee_percent_plus_flat() -> None:
    # Shopify-shaped: 2.9 % + $0.30 on $42.00 -> 1.218 + 0.30 = 1.518
    ch = _channel(
        SalesChannelFeeModel.PERCENT_PLUS_FLAT,
        fee_percent=Decimal("0.0290"),
        fee_flat=Decimal("0.30"),
    )
    assert channels_service.compute_fee(ch, Decimal("42.00")) == Decimal("1.518000")


def test_compute_fee_accepts_non_decimal_gross_amount() -> None:
    """We accept str/int/float for convenience — caller often hands in
    whatever Pydantic gave them. Internally everything coerces."""
    ch = _channel(SalesChannelFeeModel.PERCENT, fee_percent=Decimal("0.10"))
    assert channels_service.compute_fee(ch, "10.00") == Decimal("1.000000")
    assert channels_service.compute_fee(ch, 10) == Decimal("1.000000")


def test_compute_fee_quantizes_to_six_places() -> None:
    # 1/7 of 1.00 = 0.142857... — quantize to 6 places.
    ch = _channel(SalesChannelFeeModel.PERCENT, fee_percent=Decimal("1") / Decimal("7"))
    result = channels_service.compute_fee(ch, Decimal("1"))
    # Quantum is 0.000001 so the result must have exactly 6 fractional digits.
    assert -result.as_tuple().exponent == 6


def test_compute_fee_zero_gross_amount() -> None:
    ch = _channel(
        SalesChannelFeeModel.PERCENT_PLUS_FLAT,
        fee_percent=Decimal("0.05"),
        fee_flat=Decimal("0.25"),
    )
    # 5% of 0 + 0.25 = 0.25
    assert channels_service.compute_fee(ch, Decimal("0")) == Decimal("0.250000")


def test_compute_fee_flat_missing_raises() -> None:
    ch = _channel(SalesChannelFeeModel.FLAT, fee_flat=None)
    with pytest.raises(channels_service.InvalidFeeConfigurationError):
        channels_service.compute_fee(ch, Decimal("1.00"))


def test_compute_fee_percent_missing_raises() -> None:
    ch = _channel(SalesChannelFeeModel.PERCENT, fee_percent=None)
    with pytest.raises(channels_service.InvalidFeeConfigurationError):
        channels_service.compute_fee(ch, Decimal("1.00"))


def test_compute_fee_percent_plus_flat_partial_raises() -> None:
    ch = _channel(
        SalesChannelFeeModel.PERCENT_PLUS_FLAT,
        fee_percent=Decimal("0.05"),
        fee_flat=None,
    )
    with pytest.raises(channels_service.InvalidFeeConfigurationError):
        channels_service.compute_fee(ch, Decimal("1.00"))


def test_compute_fee_decimal_precision_holds_across_large_amount() -> None:
    """Sanity-check a realistic high-value sale."""
    ch = _channel(
        SalesChannelFeeModel.PERCENT_PLUS_FLAT,
        fee_percent=Decimal("0.0349"),
        fee_flat=Decimal("0.30"),
    )
    # 3.49 % of $9,876.54 = 344.691246 + 0.30 = 344.991246
    result = channels_service.compute_fee(ch, Decimal("9876.54"))
    assert result == Decimal("344.991246")
