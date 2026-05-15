"""Regression: approval payload contents must never appear in audit excerpts.

The approval-queue payload can include sensitive request snapshots
(journal-entry lines, refund details, free-text memos, customer info).
Only ``payload_summary`` (a short generic string) is allowed through to
the event log; the full payload lives on the row itself.

The whitelist registration in ``app/projections/audit/excerpts.py`` is
the load-bearing surface. This test ensures the sentinel ``DO_NOT_LEAK``
cannot escape into any of the approval-related audit rows.
"""

from __future__ import annotations

import json
import uuid

import pytest
from app.models.audit import AuditLog
from app.models.auth import Role
from app.services.approvals import ApprovalsService
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tests._approvals_helpers import seed_user
from tests._je_helpers import ensure_schema

SENTINEL = "DO_NOT_LEAK"


@pytest.mark.asyncio
async def test_sensitive_payload_never_appears_in_audit(session: AsyncSession, engine) -> None:
    await ensure_schema(engine)
    requester = await seed_user(session, email="r@x.com", role=Role.OWNER)
    approver = await seed_user(session, email="a@x.com", role=Role.OWNER)

    sensitive_payload = {
        "sensitive": SENTINEL,
        "memo": f"this includes {SENTINEL} as inline text",
        "lines": [{"description": SENTINEL}],
    }

    req = await ApprovalsService.create(
        request_type="accounting.large_journal_entry",
        subject_kind="journal_entry",
        subject_id=uuid.uuid4(),
        payload=sensitive_payload,
        session=session,
        actor_user_id=requester.id,
    )
    await ApprovalsService.approve(
        req.id,
        session=session,
        approver_user_id=approver.id,
        decision_note="ok",
    )
    await session.commit()

    rows = (
        (await session.execute(select(AuditLog).where(AuditLog.aggregate_id == req.id)))
        .scalars()
        .all()
    )
    assert rows, "expected audit rows for the approval"

    for row in rows:
        excerpt_json = json.dumps(row.payload_excerpt) if row.payload_excerpt else ""
        assert SENTINEL not in excerpt_json, (
            f"sentinel leaked into excerpt for event {row.event_type}: " f"{row.payload_excerpt!r}"
        )
        assert SENTINEL not in (row.summary or ""), (
            f"sentinel leaked into summary for event {row.event_type}: " f"{row.summary!r}"
        )
