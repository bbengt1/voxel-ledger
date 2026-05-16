"""Audit-projection PII guard for customers (Phase 7.1, #109).

The audit excerpt for ``ar.CustomerCreated`` MUST surface only
``customer_number`` + ``display_name``. ``primary_email``, ``phone``,
``billing_address``, ``shipping_address``, and ``notes`` are PII and
must never appear, even when the event payload carries them.
"""

from __future__ import annotations

import pytest
from app.events.types import ar as ar_events
from app.projections.audit.excerpts import compute_excerpt


@pytest.mark.asyncio
async def test_customer_created_excerpt_surfaces_only_number_and_name():
    payload = {
        "customer_id": "00000000-0000-0000-0000-000000000001",
        "customer_number": "CUST-2026-0001",
        "display_name": "Acme Co.",
        "legal_name": "Acme Holdings, LLC",
        "primary_email": "ap@acme.example",
        "phone": "+1 555 0100",
        "payment_terms_days": 30,
        "default_revenue_account_id": None,
        "default_ar_account_id": None,
        "tax_profile_id": None,
        "state": "active",
    }

    excerpt = compute_excerpt(ar_events.TYPE_CUSTOMER_CREATED, payload)
    assert excerpt == {
        "customer_number": "CUST-2026-0001",
        "display_name": "Acme Co.",
    }


def test_customer_created_excerpt_never_includes_pii():
    """Defense-in-depth: even if a future payload carried address/notes
    they would not leak into the excerpt."""
    payload = {
        "customer_number": "CUST-2026-0002",
        "display_name": "Beta",
        "primary_email": "leak@example.com",
        "phone": "555",
        "billing_address": {"line1": "1 Main"},
        "shipping_address": {"line1": "2 Main"},
        "notes": "private operator notes",
    }
    excerpt = compute_excerpt(ar_events.TYPE_CUSTOMER_CREATED, payload)
    assert excerpt is not None
    for forbidden in (
        "primary_email",
        "phone",
        "billing_address",
        "shipping_address",
        "notes",
    ):
        assert forbidden not in excerpt


def test_archive_unarchive_have_no_excerpt():
    assert compute_excerpt(ar_events.TYPE_CUSTOMER_ARCHIVED, {"customer_id": "x"}) is None
    assert compute_excerpt(ar_events.TYPE_CUSTOMER_UNARCHIVED, {"customer_id": "x"}) is None
