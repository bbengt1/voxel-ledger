"""Audit-projection PII guard for fixed assets (Phase 9.1, #153).

``notes`` MUST NEVER surface in any fixed-asset audit excerpt. Payloads
may carry it for replay, but the denormalized excerpt is strictly
limited to whitelisted fields (asset_number, name, kind, asset_class,
acquisition_cost on Created).
"""

from __future__ import annotations

import pytest
from app.events.types import accounting_assets as asset_events
from app.projections.audit.excerpts import compute_excerpt


@pytest.mark.asyncio
async def test_asset_created_excerpt_whitelist_only():
    payload = {
        "asset_id": "00000000-0000-0000-0000-000000000001",
        "asset_number": "ASSET-2026-0001",
        "name": "MacBook Pro",
        "kind": "tangible",
        "asset_class": "computer",
        "acquisition_cost": "1200.000000",
        "useful_life_months": 36,
        "notes": "should never appear",
    }
    excerpt = compute_excerpt(asset_events.TYPE_ASSET_CREATED, payload)
    assert excerpt == {
        "asset_number": "ASSET-2026-0001",
        "name": "MacBook Pro",
        "kind": "tangible",
        "asset_class": "computer",
        "acquisition_cost": "1200.000000",
    }
    assert "notes" not in (excerpt or {})


def test_asset_acquired_excerpt_strips_notes():
    payload = {
        "asset_id": "x",
        "asset_number": "ASSET-2026-0002",
        "acquisition_cost": "1",
        "journal_entry_id": "je-x",
        "contra_account_id": "c-x",
        "vendor_id": None,
        "acquisition_bill_id": None,
        "acquired_on": "2026-05-18",
        "notes": "secret",
    }
    excerpt = compute_excerpt(asset_events.TYPE_ASSET_ACQUIRED, payload)
    assert excerpt is not None
    assert "notes" not in excerpt
    assert "asset_number" in excerpt
