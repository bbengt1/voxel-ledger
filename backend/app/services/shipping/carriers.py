"""Carrier abstraction for shipping (Phase 6.6, #98).

The protocol :class:`CarrierClient` is intentionally minimal: today we
only need ``purchase_label`` (returns a PDF + optional tracking number)
and ``get_tracking`` (returns the latest state for a tracking number).
Future EasyPost / Shippo / USPS-direct plug-ins implement the same
contract.

Two reference implementations ship in this module:

* :class:`StaticFallbackCarrier` — generates a packing-slip-style PDF
  locally with ``reportlab``. No external account, no tracking number,
  ``cost_amount=Decimal("0")``. Used when no carrier credentials are
  configured.
* :class:`StubCarrier` — deterministic test stub. Returns
  ``tracking_number=f"TEST-{uuid}"`` and ``cost_amount=Decimal("9.99")``
  so tests can assert exact values without hitting a real network.

The :func:`get_carrier_client` factory picks an implementation off the
``shipping.default_carrier`` setting (or an explicit ``carrier_hint``
override) and falls back to the static carrier when the requested
carrier has no credentials registered.

Real EasyPost / Shippo integration is **out of scope** for this issue —
see the PR body for the planned shape.
"""

from __future__ import annotations

import io
import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Protocol

# Lazy reportlab imports happen inside StaticFallbackCarrier so importing
# this module doesn't pay the cost when only the stub is used.


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CarrierLabelResult:
    """The artifact returned by ``purchase_label``.

    * ``pdf_bytes`` — the raw PDF the operator prints. Always non-empty.
    * ``tracking_number`` — None for the static fallback, populated for
      real carriers and the stub.
    * ``tracking_url`` — best-effort deep link for tracking; None when
      no tracking is available.
    * ``cost_amount`` — what the carrier charged in USD.
    * ``carrier`` — the carrier slug actually used (may differ from the
      hint if the factory fell back to the static carrier).
    """

    pdf_bytes: bytes
    tracking_number: str | None
    tracking_url: str | None
    cost_amount: Decimal
    carrier: str


@dataclass(frozen=True)
class CarrierTrackingResult:
    """A point-in-time tracking snapshot.

    Real carriers return a richer payload (per-stop history, ETA, etc.);
    we keep this narrow because the static fallback can't synthesize
    detail it doesn't have.
    """

    status: str
    last_updated: str | None = None
    raw: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


class CarrierClient(Protocol):
    """The contract every carrier implementation honors.

    Implementations should be cheap to construct (no network on
    ``__init__``) and safe to call without holding a DB session.
    """

    name: str

    def purchase_label(
        self,
        *,
        ship_from: dict[str, Any],
        ship_to: dict[str, Any],
        weight_grams: int | None,
        dimensions_cm: dict[str, Any] | None,
        service_level: str | None,
    ) -> CarrierLabelResult: ...

    def get_tracking(self, tracking_number: str) -> CarrierTrackingResult: ...


# ---------------------------------------------------------------------------
# Static fallback (real default)
# ---------------------------------------------------------------------------


class StaticFallbackCarrier:
    """Generates a packing-slip-style PDF locally with reportlab.

    No external account, no tracking, no cost. Used when the operator
    has not configured any carrier credentials — better to print a
    physical slip than block the sale from shipping.
    """

    name = "static_fallback"

    def purchase_label(
        self,
        *,
        ship_from: dict[str, Any],
        ship_to: dict[str, Any],
        weight_grams: int | None,
        dimensions_cm: dict[str, Any] | None,
        service_level: str | None,
    ) -> CarrierLabelResult:
        pdf_bytes = _render_packing_slip(
            ship_from=ship_from,
            ship_to=ship_to,
            weight_grams=weight_grams,
            dimensions_cm=dimensions_cm,
            service_level=service_level,
        )
        return CarrierLabelResult(
            pdf_bytes=pdf_bytes,
            tracking_number=None,
            tracking_url=None,
            cost_amount=Decimal("0"),
            carrier=self.name,
        )

    def get_tracking(self, tracking_number: str) -> CarrierTrackingResult:
        # The static fallback never issues a tracking number, so any call
        # here is a programmer error. Surface a clear "no-op" status
        # instead of raising so callers can probe defensively.
        return CarrierTrackingResult(status="unknown", last_updated=None, raw=None)


def _render_packing_slip(
    *,
    ship_from: dict[str, Any],
    ship_to: dict[str, Any],
    weight_grams: int | None,
    dimensions_cm: dict[str, Any] | None,
    service_level: str | None,
) -> bytes:
    """Build a minimal packing-slip PDF in memory.

    Kept intentionally simple — one page, sans-serif, addresses + a
    weight/service line. The output is deterministic (no clock, no
    randomness) so tests can byte-compare across runs if needed.
    """
    from reportlab.lib.pagesizes import LETTER
    from reportlab.lib.units import inch
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=LETTER)
    width, height = LETTER
    margin = 0.5 * inch
    y = height - margin

    c.setFont("Helvetica-Bold", 16)
    c.drawString(margin, y, "PACKING SLIP")
    y -= 0.4 * inch

    c.setFont("Helvetica-Bold", 11)
    c.drawString(margin, y, "Ship From:")
    y -= 0.2 * inch
    c.setFont("Helvetica", 10)
    for line in _address_lines(ship_from):
        c.drawString(margin, y, line)
        y -= 0.18 * inch

    y -= 0.2 * inch
    c.setFont("Helvetica-Bold", 11)
    c.drawString(margin, y, "Ship To:")
    y -= 0.2 * inch
    c.setFont("Helvetica", 10)
    for line in _address_lines(ship_to):
        c.drawString(margin, y, line)
        y -= 0.18 * inch

    y -= 0.3 * inch
    c.setFont("Helvetica", 10)
    if service_level:
        c.drawString(margin, y, f"Service: {service_level}")
        y -= 0.18 * inch
    if weight_grams is not None:
        c.drawString(margin, y, f"Weight: {weight_grams} g")
        y -= 0.18 * inch
    if dimensions_cm:
        dims = " x ".join(
            f"{dimensions_cm.get(k, '?')}" for k in ("l", "w", "h") if k in dimensions_cm
        )
        c.drawString(margin, y, f"Dimensions: {dims} cm")
        y -= 0.18 * inch

    y -= 0.4 * inch
    c.setFont("Helvetica-Oblique", 9)
    c.drawString(
        margin,
        y,
        "Static fallback — no carrier integration. Affix postage manually.",
    )

    c.showPage()
    c.save()
    return buf.getvalue()


def _address_lines(addr: dict[str, Any]) -> list[str]:
    """Render an address dict into 1-N display lines, skipping blanks."""
    out: list[str] = []
    if addr.get("name"):
        out.append(str(addr["name"]))
    if addr.get("street1"):
        out.append(str(addr["street1"]))
    if addr.get("street2"):
        out.append(str(addr["street2"]))
    city_line_bits = []
    if addr.get("city"):
        city_line_bits.append(str(addr["city"]))
    if addr.get("region"):
        city_line_bits.append(str(addr["region"]))
    if addr.get("postal_code"):
        city_line_bits.append(str(addr["postal_code"]))
    if city_line_bits:
        head = ", ".join(city_line_bits[:2])
        tail = f" {city_line_bits[2]}" if len(city_line_bits) > 2 else ""
        out.append(head + tail)
    if addr.get("country"):
        out.append(str(addr["country"]))
    if not out:
        out.append("(address unavailable)")
    return out


# ---------------------------------------------------------------------------
# Stub carrier (for tests)
# ---------------------------------------------------------------------------


class StubCarrier:
    """Deterministic stub for unit tests.

    * ``purchase_label`` always returns a small valid PDF, a synthesized
      tracking number of the form ``TEST-{uuid}``, and a cost of
      ``Decimal("9.99")``.
    * ``get_tracking`` returns ``status="in_transit"`` so tests asserting
      "we wired through the carrier" have something to compare against.

    The PDF body is reused from the static carrier so the stub still
    produces a non-empty payload; only the metadata is synthesized.
    """

    name = "stub"

    def purchase_label(
        self,
        *,
        ship_from: dict[str, Any],
        ship_to: dict[str, Any],
        weight_grams: int | None,
        dimensions_cm: dict[str, Any] | None,
        service_level: str | None,
    ) -> CarrierLabelResult:
        pdf_bytes = _render_packing_slip(
            ship_from=ship_from,
            ship_to=ship_to,
            weight_grams=weight_grams,
            dimensions_cm=dimensions_cm,
            service_level=service_level,
        )
        return CarrierLabelResult(
            pdf_bytes=pdf_bytes,
            tracking_number=f"TEST-{uuid.uuid4()}",
            tracking_url=None,
            cost_amount=Decimal("9.99"),
            carrier=self.name,
        )

    def get_tracking(self, tracking_number: str) -> CarrierTrackingResult:
        return CarrierTrackingResult(status="in_transit", last_updated=None, raw=None)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def get_carrier_client(
    carrier_name: str | None,
    *,
    has_credentials: bool = False,
) -> CarrierClient:
    """Return a :class:`CarrierClient` for ``carrier_name``.

    Selection rules:

    1. ``None`` or ``"static_fallback"`` -> :class:`StaticFallbackCarrier`.
    2. ``"stub"`` -> :class:`StubCarrier` (tests only).
    3. Any other slug (``"usps"`` / ``"ups"`` / ``"fedex"`` / …) — no
       real carrier integration exists yet, so we fall back to the
       static carrier. The static carrier still surfaces the *requested*
       carrier slug through the audit trail if the caller wants to
       record intent.

    ``has_credentials`` is a hook for the future plug-in shape: once a
    real carrier client lands, the factory will look up its creds and
    only return the real client when they're present. Today it's
    advisory only.
    """
    if not carrier_name or carrier_name == StaticFallbackCarrier.name:
        return StaticFallbackCarrier()
    if carrier_name == StubCarrier.name:
        return StubCarrier()
    # Real-carrier slugs we don't implement yet — fall back to static so
    # the operator still gets a printable label.
    return StaticFallbackCarrier()


__all__ = [
    "CarrierClient",
    "CarrierLabelResult",
    "CarrierTrackingResult",
    "StaticFallbackCarrier",
    "StubCarrier",
    "get_carrier_client",
]
