"""Audit-projection PII guard for vendors (Phase 8.1, #128).

The audit excerpt for ``ap.VendorCreated`` MUST surface only
``vendor_number`` + ``display_name``. ``primary_email``, ``phone``,
``billing_address``, ``shipping_address``, ``tax_id``, and ``notes`` are
PII and must never appear, even when the event payload carries them.
"""

from __future__ import annotations

import pytest
from app.events.types import ap as ap_events
from app.projections.audit.excerpts import compute_excerpt


@pytest.mark.asyncio
async def test_vendor_created_excerpt_surfaces_only_number_and_name():
    payload = {
        "vendor_id": "00000000-0000-0000-0000-000000000001",
        "vendor_number": "VEND-2026-0001",
        "display_name": "Acme Supplies",
        "legal_name": "Acme Supplies, LLC",
        "primary_email": "ar@acmesupp.example",
        "phone": "+1 555 0100",
        "payment_terms_days": 30,
        "default_expense_account_id": None,
        "default_ap_account_id": None,
        "tax_id": "12-3456789",
        "is_1099_vendor": False,
        "state": "active",
    }

    excerpt = compute_excerpt(ap_events.TYPE_VENDOR_CREATED, payload)
    assert excerpt == {
        "vendor_number": "VEND-2026-0001",
        "display_name": "Acme Supplies",
    }


def test_vendor_created_excerpt_never_includes_pii():
    """Defense-in-depth: even if a future payload carried PII fields they
    would not leak into the excerpt."""
    payload = {
        "vendor_number": "VEND-2026-0002",
        "display_name": "Beta",
        "primary_email": "leak@example.com",
        "phone": "555",
        "billing_address": {"line1": "1 Main"},
        "shipping_address": {"line1": "2 Main"},
        "tax_id": "99-9999999",
        "notes": "private operator notes",
    }
    excerpt = compute_excerpt(ap_events.TYPE_VENDOR_CREATED, payload)
    assert excerpt is not None
    for forbidden in (
        "primary_email",
        "phone",
        "billing_address",
        "shipping_address",
        "tax_id",
        "notes",
    ):
        assert forbidden not in excerpt


def test_archive_unarchive_have_no_excerpt():
    assert compute_excerpt(ap_events.TYPE_VENDOR_ARCHIVED, {"vendor_id": "x"}) is None
    assert compute_excerpt(ap_events.TYPE_VENDOR_UNARCHIVED, {"vendor_id": "x"}) is None
