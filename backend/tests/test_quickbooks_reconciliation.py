"""QBO reconciliation / completeness + decommission gate — Phase 4b (#317).

Covers gap detection via outbox coverage (a finalized record with no synced
outbox row), drift folding (open CDC drift blocks the gate), the
decommission-ready conjunction, and the owner-only admin endpoints.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from app.models.auth import Role, User
from app.models.qbo_cdc_drift import QboCdcDrift, QboDriftStatus
from app.models.qbo_sync_outbox import QboSyncOutbox, QboSyncStatus
from app.services.auth import create_user
from app.services.quickbooks import reconcile
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tests._je_helpers import seed_owner

QB = "/api/v1/admin/quickbooks"
NOW = datetime(2026, 6, 10, 12, 0, 0, tzinfo=UTC)


async def _seed_login(role: Role, client: AsyncClient, session: AsyncSession) -> str:
    email = f"{role.value}@example.com"
    await create_user(
        session,
        email=email,
        password="pw-correct",
        full_name=role.value,
        role=role,
        bcrypt_rounds=4,
    )
    await session.commit()
    r = await client.post("/api/v1/auth/login", json={"email": email, "password": "pw-correct"})
    return r.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _make_invoice(session: AsyncSession, *, issued: bool, number: str) -> uuid.UUID:
    """Minimal issued Invoice row to exercise gap detection on kind='invoice'."""
    from app.models.invoice import Invoice, InvoiceState

    user = (await session.execute(select(User))).scalars().first()
    inv = Invoice(
        id=uuid.uuid4(),
        invoice_number=number,
        customer_id=uuid.uuid4(),
        state=InvoiceState.ISSUED.value if issued else InvoiceState.DRAFT.value,
        issued_at=NOW if issued else None,
        created_by_user_id=user.id if user else None,
    )
    session.add(inv)
    await session.flush()
    return inv.id


async def _synced_outbox(session: AsyncSession, *, kind: str, local_id: uuid.UUID) -> None:
    session.add(
        QboSyncOutbox(
            kind=kind,
            local_id=local_id,
            op="post",
            payload={"lines": []},
            request_id=uuid.uuid4().hex,
            status=QboSyncStatus.SYNCED.value,
            qbo_entity_type="Invoice",
            qbo_id="900",
        )
    )
    await session.flush()


async def _matched_bank_tx(session: AsyncSession, *, linked: bool) -> uuid.UUID:
    """A MATCHED bank transaction. ``linked=True`` simulates a match to an
    existing journal line (no JE enqueued); ``linked=False`` is a QBO-mode
    post_to_account match (bank_match enqueued, matched_journal_line_id NULL)."""
    from app.models.bank import BankTransaction, BankTransactionState

    tx = BankTransaction(
        id=uuid.uuid4(),
        account_id=uuid.uuid4(),
        occurred_on=NOW.date(),
        amount=100,
        external_hash=uuid.uuid4().hex,
        state=BankTransactionState.MATCHED.value,
        matched_journal_line_id=uuid.uuid4() if linked else None,
    )
    tx.created_at = NOW
    session.add(tx)
    await session.flush()
    return tx.id


# --------------------------------------------------------------------------- #
# service: gap detection + gate
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_issued_invoice_without_synced_row_is_a_gap(app_session: AsyncSession) -> None:
    await seed_owner(app_session)
    inv_id = await _make_invoice(app_session, issued=True, number="INV-1")
    await app_session.commit()

    report = await reconcile.build(app_session, date_from=NOW.date(), date_to=NOW.date())
    gap_ids = {g.local_id for g in report.gaps}
    assert str(inv_id) in gap_ids
    assert report.gap_count >= 1
    assert report.decommission_ready is False


@pytest.mark.asyncio
async def test_draft_invoice_is_not_a_gap(app_session: AsyncSession) -> None:
    await seed_owner(app_session)
    await _make_invoice(app_session, issued=False, number="INV-DRAFT")
    await app_session.commit()
    report = await reconcile.build(app_session, date_from=NOW.date(), date_to=NOW.date())
    assert all(g.kind != "invoice" for g in report.gaps)


@pytest.mark.asyncio
async def test_synced_invoice_closes_the_gap(app_session: AsyncSession) -> None:
    await seed_owner(app_session)
    inv_id = await _make_invoice(app_session, issued=True, number="INV-2")
    await _synced_outbox(app_session, kind="invoice", local_id=inv_id)
    await app_session.commit()
    report = await reconcile.build(app_session, date_from=NOW.date(), date_to=NOW.date())
    assert str(inv_id) not in {g.local_id for g in report.gaps}


@pytest.mark.asyncio
async def test_decommission_ready_when_clean(app_session: AsyncSession) -> None:
    await seed_owner(app_session)
    # Empty books, drained outbox, no drift → ready.
    report = await reconcile.build(app_session, date_from=NOW.date(), date_to=NOW.date())
    assert report.gap_count == 0
    assert report.drift_open == 0
    assert report.decommission_ready is True


@pytest.mark.asyncio
async def test_pending_outbox_blocks_gate(app_session: AsyncSession) -> None:
    await seed_owner(app_session)
    app_session.add(
        QboSyncOutbox(
            kind="invoice",
            local_id=uuid.uuid4(),
            op="post",
            payload={},
            request_id=uuid.uuid4().hex,
            status=QboSyncStatus.PENDING.value,
        )
    )
    await app_session.commit()
    report = await reconcile.build(app_session, date_from=NOW.date(), date_to=NOW.date())
    assert report.decommission_ready is False


@pytest.mark.asyncio
async def test_open_drift_blocks_gate_and_counts_mismatch(app_session: AsyncSession) -> None:
    await seed_owner(app_session)
    app_session.add(
        QboCdcDrift(
            entity_type="Invoice",
            qbo_id="555",
            change_type="updated",
            local_kind="invoice",
            local_id=uuid.uuid4(),
            occurrences=1,
            status=QboDriftStatus.OPEN.value,
            first_detected_at=NOW,
            last_detected_at=NOW,
        )
    )
    await app_session.commit()
    report = await reconcile.build(app_session, date_from=NOW.date(), date_to=NOW.date())
    assert report.drift_open == 1
    assert report.mismatch_candidates == 1  # change_type == "updated"
    assert report.decommission_ready is False


@pytest.mark.asyncio
async def test_bank_match_unsynced_is_a_gap(app_session: AsyncSession) -> None:
    await seed_owner(app_session)
    tx_id = await _matched_bank_tx(app_session, linked=False)
    await app_session.commit()
    report = await reconcile.build(app_session, date_from=NOW.date(), date_to=NOW.date())
    assert str(tx_id) in {g.local_id for g in report.gaps if g.kind == "bank_match"}


@pytest.mark.asyncio
async def test_bank_match_linked_to_existing_line_is_not_a_gap(
    app_session: AsyncSession,
) -> None:
    await seed_owner(app_session)
    # Match to an existing journal line → no JE enqueued → must not be a gap.
    await _matched_bank_tx(app_session, linked=True)
    await app_session.commit()
    report = await reconcile.build(app_session, date_from=NOW.date(), date_to=NOW.date())
    assert all(g.kind != "bank_match" for g in report.gaps)


@pytest.mark.asyncio
async def test_bank_match_synced_closes_gap(app_session: AsyncSession) -> None:
    await seed_owner(app_session)
    tx_id = await _matched_bank_tx(app_session, linked=False)
    await _synced_outbox(app_session, kind="bank_match", local_id=tx_id)
    await app_session.commit()
    report = await reconcile.build(app_session, date_from=NOW.date(), date_to=NOW.date())
    assert all(g.kind != "bank_match" for g in report.gaps)


# --------------------------------------------------------------------------- #
# API
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_reconciliation_requires_owner(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    token = await _seed_login(Role.BOOKKEEPER, client, app_session)
    r = await client.get(f"{QB}/reconciliation", headers=_auth(token))
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_reconciliation_endpoint_default_range(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    token = await _seed_login(Role.OWNER, client, app_session)
    r = await client.get(f"{QB}/reconciliation", headers=_auth(token))
    assert r.status_code == 200, r.text
    body = r.json()
    assert "decommission_ready" in body
    assert "outbox" in body and "gap_count" in body and "drift_open" in body


@pytest.mark.asyncio
async def test_reconciliation_bad_range(client: AsyncClient, app_session: AsyncSession) -> None:
    token = await _seed_login(Role.OWNER, client, app_session)
    r = await client.get(
        f"{QB}/reconciliation",
        params={"from": "2026-06-10", "to": "2026-06-01"},
        headers=_auth(token),
    )
    assert r.status_code == 400, r.text


@pytest.mark.asyncio
async def test_drift_list_and_acknowledge(client: AsyncClient, app_session: AsyncSession) -> None:
    token = await _seed_login(Role.OWNER, client, app_session)
    drift = QboCdcDrift(
        entity_type="Payment",
        qbo_id="777",
        change_type="deleted",
        local_kind="payment",
        local_id=uuid.uuid4(),
        occurrences=2,
        status=QboDriftStatus.OPEN.value,
        first_detected_at=NOW,
        last_detected_at=NOW,
    )
    app_session.add(drift)
    await app_session.commit()

    r = await client.get(f"{QB}/drift", params={"status": "open"}, headers=_auth(token))
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    assert len(items) == 1 and items[0]["qbo_id"] == "777"

    r = await client.post(f"{QB}/drift/{drift.id}/acknowledge", headers=_auth(token))
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "acknowledged"

    refreshed = (
        await app_session.execute(select(QboCdcDrift).where(QboCdcDrift.id == drift.id))
    ).scalar_one()
    await app_session.refresh(refreshed)
    assert refreshed.status == QboDriftStatus.ACKNOWLEDGED.value


@pytest.mark.asyncio
async def test_drift_acknowledge_404(client: AsyncClient, app_session: AsyncSession) -> None:
    token = await _seed_login(Role.OWNER, client, app_session)
    r = await client.post(f"{QB}/drift/{uuid.uuid4()}/acknowledge", headers=_auth(token))
    assert r.status_code == 404, r.text
