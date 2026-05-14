"""Schema registry for operational settings.

Each setting is a subclass of :class:`SettingSchema` declaring a
``key`` (namespaced dotted string), a ``default``, and a single ``value``
field whose Pydantic type is the storage type. The class itself is what
validates writes and provides defaults on reads.

Registration is decorator-driven. Importing this module is sufficient to
populate the registry because every concrete schema applies ``@register``
at class-definition time.

Decimal handling
----------------
For monetary / rate values we use ``pydantic.Decimal``. Storage encodes a
decimal as its canonical string (``Decimal.to_eng_string`` or ``str``);
the service layer round-trips through ``Decimal(stored_str)`` so precision
survives the JSON layer. Pydantic itself does the string-to-Decimal
coercion during validation.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict, Field


class UnknownSettingError(KeyError):
    """Lookup or write attempted against a key not in the registry."""


class SettingSchema(BaseModel):
    """Base for one typed operational setting.

    Subclasses MUST set the class variables ``key`` and ``default`` and
    declare a single ``value`` field whose annotation is the storage type.
    The schema is constructed as ``MySchema(value=raw)`` to validate; the
    validated ``.value`` attribute is what we persist (and the type the
    service returns to callers).
    """

    # Pydantic-side config: allow arbitrary types so dicts/decimals work
    # without bespoke encoders. Strict on extras — refuse unknown fields.
    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    # ClassVar markers — concrete subclasses fill these in.
    key: ClassVar[str]
    default: ClassVar[Any]

    # Subclasses redeclare ``value`` with the actual storage type.
    value: Any


_REGISTRY: dict[str, type[SettingSchema]] = {}


def register(schema_cls: type[SettingSchema]) -> type[SettingSchema]:
    """Decorator: register a schema class under its ``key``.

    Re-registering the same class is a no-op (test re-imports). Two
    different classes claiming the same key is a programmer error and
    raises at import time.
    """
    key = getattr(schema_cls, "key", None)
    if not isinstance(key, str) or not key:
        raise TypeError(f"{schema_cls.__name__} must declare a non-empty class-level `key`")
    existing = _REGISTRY.get(key)
    if existing is schema_cls:
        return schema_cls
    if existing is not None:
        raise RuntimeError(
            f"setting key {key!r} already registered to "
            f"{existing.__name__}; cannot also bind {schema_cls.__name__}"
        )
    _REGISTRY[key] = schema_cls
    return schema_cls


def get_schema(key: str) -> type[SettingSchema]:
    """Return the registered schema for ``key`` or raise."""
    try:
        return _REGISTRY[key]
    except KeyError as exc:
        raise UnknownSettingError(f"unknown setting key {key!r}") from exc


def all_schemas() -> dict[str, type[SettingSchema]]:
    """Snapshot of the registry, sorted by key for stable iteration."""
    return dict(sorted(_REGISTRY.items()))


def _is_registered(key: str) -> bool:
    return key in _REGISTRY


def _reset_for_tests() -> None:
    """Test helper. Not exported.

    Doesn't actually clear since concrete schemas register at import time
    and re-importing wouldn't repopulate after a wipe. Provided for
    symmetry only.
    """
    return None


# ---------------------------------------------------------------------------
# Concrete settings.
#
# Each class declares `key`, `default`, and a `value` field. The decorator
# wires it into the registry on import. Group by namespace so the registry
# stays easy to scan.
# ---------------------------------------------------------------------------


@register
class LaborRatePerHour(SettingSchema):
    """Hourly labor cost used by the cost engine (USD/hour)."""

    key: ClassVar[str] = "cost_engine.labor_rate_per_hour"
    default: ClassVar[Decimal] = Decimal("25.00")
    value: Decimal = Field(ge=0)


@register
class MachineRatePerHour(SettingSchema):
    """Hourly machine cost used by the cost engine (USD/hour)."""

    key: ClassVar[str] = "cost_engine.machine_rate_per_hour"
    default: ClassVar[Decimal] = Decimal("1.00")
    value: Decimal = Field(ge=0)


@register
class OverheadPercent(SettingSchema):
    """Overhead surcharge applied by the cost engine (percent, 0-100)."""

    key: ClassVar[str] = "cost_engine.overhead_percent"
    default: ClassVar[Decimal] = Decimal("15.00")
    value: Decimal = Field(ge=0, le=100)


@register
class PowerCostPerKwh(SettingSchema):
    """Power cost used by the cost engine (USD/kWh)."""

    key: ClassVar[str] = "cost_engine.power_cost_per_kwh"
    default: ClassVar[Decimal] = Decimal("0.12")
    value: Decimal = Field(ge=0)


@register
class DefaultMarginPercent(SettingSchema):
    """Default margin applied by quote/job pricing (percent, 0-100)."""

    key: ClassVar[str] = "cost_engine.default_margin_percent"
    default: ClassVar[Decimal] = Decimal("30.00")
    value: Decimal = Field(ge=0, le=100)


@register
class BarcodeScanPadding(SettingSchema):
    """Pad character prepended to short barcode scans at POS.

    Stored as a string so the operator can pick ``"0"``, ``""``, or even
    a multi-character prefix without changing the schema.
    """

    key: ClassVar[str] = "pos.barcode_scan_padding"
    default: ClassVar[str] = "0"
    value: str


@register
class AttachmentsStorageRoot(SettingSchema):
    """Filesystem root for uploaded attachments (Phase 2.6).

    Stored as a string so contributors can override in local dev to a
    path like ``./data/attachments`` (which should be gitignored). In
    prod we deploy with ``/srv/3d-print-sales/data/attachments``. The
    attachments service joins ``{YYYY}/{MM}/{uuid}-{slug}`` underneath.
    """

    key: ClassVar[str] = "attachments.storage_root"
    default: ClassVar[str] = "/srv/3d-print-sales/data/attachments"
    value: str = Field(min_length=1)


@register
class ReferencePaddingWidth(SettingSchema):
    """Per-prefix padding width for the reference-number allocator.

    Keys are prefixes (``S``, ``INV``, ``Q``, ``BILL``); values are the
    zero-padded numeric width. The allocator falls back to the schema
    default for any prefix not present in the stored dict.
    """

    key: ClassVar[str] = "reference.padding_width"
    default: ClassVar[dict[str, int]] = {"S": 4, "INV": 4, "Q": 4, "BILL": 4}
    value: dict[str, int]
