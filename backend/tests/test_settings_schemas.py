"""Schema registry tests for operational settings.

Confirm: every registry entry has a default, validation rejects bad
types / out-of-range values, unknown keys raise.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from app.services.settings.schemas import (
    UnknownSettingError,
    all_schemas,
    get_schema,
)
from pydantic import ValidationError


def test_all_schemas_have_defaults() -> None:
    """Every registered schema declares a class-level ``default``."""
    schemas = all_schemas()
    assert schemas  # not empty
    for key, cls in schemas.items():
        assert hasattr(cls, "default"), f"{key} missing default"
        # The default itself must validate against the schema; if it
        # doesn't, the "fall back to default" read path returns garbage.
        validated = cls(value=cls.default)
        assert validated.value == cls.default or isinstance(validated.value, type(cls.default))


def test_known_cost_engine_keys_present() -> None:
    keys = set(all_schemas())
    expected = {
        "cost_engine.labor_rate_per_hour",
        "cost_engine.machine_rate_per_hour",
        "cost_engine.overhead_percent",
        "cost_engine.power_cost_per_kwh",
        "cost_engine.default_margin_percent",
        "pos.barcode_scan_padding",
        "reference.padding_width",
    }
    assert expected.issubset(keys)


def test_unknown_key_raises() -> None:
    with pytest.raises(UnknownSettingError):
        get_schema("not.a.real.key")


def test_decimal_setting_accepts_string_and_decimal() -> None:
    schema = get_schema("cost_engine.labor_rate_per_hour")
    assert schema(value="42.50").value == Decimal("42.50")
    assert schema(value=Decimal("42.50")).value == Decimal("42.50")


def test_decimal_setting_rejects_negative() -> None:
    schema = get_schema("cost_engine.labor_rate_per_hour")
    with pytest.raises(ValidationError):
        schema(value="-1.00")


def test_overhead_percent_capped_at_100() -> None:
    schema = get_schema("cost_engine.overhead_percent")
    assert schema(value="100").value == Decimal("100")
    with pytest.raises(ValidationError):
        schema(value="101")


def test_reference_padding_width_accepts_dict() -> None:
    schema = get_schema("reference.padding_width")
    val = schema(value={"S": 5, "INV": 4}).value
    assert val == {"S": 5, "INV": 4}


def test_reference_padding_width_rejects_non_int_values() -> None:
    schema = get_schema("reference.padding_width")
    with pytest.raises(ValidationError):
        schema(value={"S": "not-an-int"})


def test_barcode_scan_padding_string_type() -> None:
    schema = get_schema("pos.barcode_scan_padding")
    assert schema(value="00").value == "00"
    # ``str`` is permissive: even an empty string is allowed (operator may
    # disable padding outright).
    assert schema(value="").value == ""
