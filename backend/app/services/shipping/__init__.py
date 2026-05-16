"""Shipping module (Phase 6.6, #98).

Public entry points:

* ``service`` — high-level CRUD + state-machine for ``shipment``.
* ``carriers`` — pluggable carrier abstraction (static fallback today,
  real EasyPost/Shippo plug-ins are a Phase 6.7+ concern).
* ``storage`` — file-storage helpers for label PDFs.

The top-level module re-exports the service so callers can write
``from app.services import shipping`` and call ``shipping.create_shipment``
without reaching into the submodule.
"""

from __future__ import annotations

from app.services.shipping.service import (
    InvalidShipmentStateError,
    LabelNotAvailableError,
    ShipmentNotFoundError,
    ShippingServiceError,
    cancel,
    create_shipment,
    get,
    list_for_sale,
    load_label_pdf,
    mark_delivered,
    mark_shipped,
    purchase_label,
)

__all__ = [
    "InvalidShipmentStateError",
    "LabelNotAvailableError",
    "ShipmentNotFoundError",
    "ShippingServiceError",
    "cancel",
    "create_shipment",
    "get",
    "list_for_sale",
    "load_label_pdf",
    "mark_delivered",
    "mark_shipped",
    "purchase_label",
]
