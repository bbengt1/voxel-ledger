"""Audit-projection PII guard for expense categories (Phase 8.6, #133).

The audit excerpt for ``ap.ExpenseCategoryCreated`` and
``ap.ExpenseCategoryArchived`` MUST surface only ``code`` + ``name``.
``notes`` is an operator-only free-form field and must never appear,
even when the event payload carries it.
"""

from __future__ import annotations

from app.events.types import ap as ap_events
from app.projections.audit.excerpts import compute_excerpt


def test_expense_category_created_excerpt_omits_notes():
    payload = {
        "expense_category_id": "00000000-0000-0000-0000-000000000001",
        "code": "TRAVEL",
        "name": "Travel",
        "default_expense_account_id": "00000000-0000-0000-0000-000000000002",
        "parent_id": None,
        "is_active": True,
        "notes": "secret operator note",
    }
    excerpt = compute_excerpt(ap_events.TYPE_EXPENSE_CATEGORY_CREATED, payload)
    assert excerpt == {"code": "TRAVEL", "name": "Travel"}
    assert "notes" not in (excerpt or {})


def test_expense_category_archived_excerpt_safe():
    payload = {
        "expense_category_id": "00000000-0000-0000-0000-000000000001",
        "code": "OLD",
        "name": "Old",
    }
    excerpt = compute_excerpt(ap_events.TYPE_EXPENSE_CATEGORY_ARCHIVED, payload)
    assert excerpt == {"code": "OLD", "name": "Old"}
