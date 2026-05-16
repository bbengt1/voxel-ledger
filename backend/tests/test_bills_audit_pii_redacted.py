"""Audit-projection PII guard for bills (Phase 8.2, #129).

The audit excerpt for ``ap.BillCreated`` MUST NOT surface ``notes`` or
``billing_address_snapshot``. The event payload carries them so replay
can reconstruct the bill, but the denormalized audit excerpt keeps
strictly to bill_number / vendor_id / total_amount / due_at /
vendor_invoice_number.
"""

from __future__ import annotations

import pytest
from app.events.types import ap as ap_events
from app.projections.audit.excerpts import compute_excerpt


@pytest.mark.asyncio
async def test_bill_created_excerpt_surfaces_only_whitelisted():
    payload = {
        "bill_id": "00000000-0000-0000-0000-000000000001",
        "bill_number": "BILL-2026-0001",
        "vendor_id": "00000000-0000-0000-0000-000000000002",
        "state": "draft",
        "issued_at": None,
        "due_at": "2026-06-01T00:00:00+00:00",
        "vendor_invoice_number": "VEND-INV-9",
        "subtotal": "100.000000",
        "discount_amount": "0",
        "tax_amount": "5.000000",
        "total_amount": "105.000000",
        "currency": "USD",
        "notes": "private operator notes",
        "billing_address_snapshot": {"line1": "1 Main"},
        "items": [],
    }

    excerpt = compute_excerpt(ap_events.TYPE_BILL_CREATED, payload)
    assert excerpt == {
        "bill_number": "BILL-2026-0001",
        "vendor_id": "00000000-0000-0000-0000-000000000002",
        "total_amount": "105.000000",
        "due_at": "2026-06-01T00:00:00+00:00",
        "vendor_invoice_number": "VEND-INV-9",
    }


def test_bill_created_excerpt_never_includes_pii():
    payload = {
        "bill_number": "BILL-2026-0002",
        "vendor_id": "x",
        "total_amount": "1",
        "due_at": None,
        "vendor_invoice_number": None,
        "notes": "private",
        "billing_address_snapshot": {"line1": "leak"},
    }
    excerpt = compute_excerpt(ap_events.TYPE_BILL_CREATED, payload)
    assert excerpt is not None
    for forbidden in ("notes", "billing_address_snapshot"):
        assert forbidden not in excerpt


def test_bill_issued_excerpt_minimal():
    payload = {
        "bill_id": "x",
        "bill_number": "BILL-2026-0003",
        "vendor_id": "v",
        "total_amount": "1",
        "issued_at": "2026-05-16T00:00:00+00:00",
        "due_at": None,
        "journal_entry_id": "j",
    }
    excerpt = compute_excerpt(ap_events.TYPE_BILL_ISSUED, payload)
    assert excerpt is not None
    assert "bill_number" in excerpt
    assert "journal_entry_id" in excerpt
    assert "notes" not in excerpt
