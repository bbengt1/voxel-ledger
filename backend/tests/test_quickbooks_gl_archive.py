"""Local-GL archive/export for decommission (#318, epic #312, Phase 5a).

The archive is the audit record + down-migration recovery path produced before
the GL is dropped. These tests cover:

* ``build_archive`` writes a CSV dump of every GL table + a trial-balance
  snapshot, fingerprints them, and persists a balanced manifest;
* the owner-only admin endpoint triggers an archive and lists prior runs.
"""

from __future__ import annotations

import csv
import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from app.models.auth import Role
from app.services import journal_entries as journal_service
from app.services.quickbooks import archive
from app.services.settings.service import SettingsService
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests._banking_helpers import auth_header, token_for
from tests._je_helpers import d, seed_account, seed_owner


async def _post_je(session: AsyncSession, *, actor_user_id, lines) -> None:
    journal_lines = [
        journal_service.JournalLineInput(
            account_id=acct_id, debit=d(dr), credit=d(cr), line_number=i
        )
        for i, (acct_id, dr, cr) in enumerate(lines, start=1)
    ]
    await journal_service.post(
        journal_service.JournalEntryInput(
            description="seed",
            posted_at=datetime.now(UTC),
            lines=journal_lines,
        ),
        session=session,
        actor_user_id=actor_user_id,
        _internal_skip_approval_check=True,
    )
    await session.flush()


@pytest.mark.asyncio
async def test_build_archive_writes_artifacts_and_manifest(
    app_session: AsyncSession, tmp_path: Path
) -> None:
    user = await seed_owner(app_session)
    bank = await seed_account(app_session, code="1000", name="Bank", type="asset")
    revenue = await seed_account(app_session, code="4000", name="Sales", type="revenue")
    await _post_je(
        app_session,
        actor_user_id=user.id,
        lines=[(bank.id, "100.00", "0"), (revenue.id, "0", "100.00")],
    )
    await app_session.commit()

    out_dir = tmp_path / "archive"
    manifest = await archive.build_archive(
        app_session, cutover_date=datetime.now(UTC).date(), out_dir=out_dir, actor_user_id=user.id
    )
    await app_session.commit()

    # All GL tables + the trial-balance snapshot were written.
    for fname in (
        "account.csv",
        "account_balance.csv",
        "journal_entry.csv",
        "journal_line.csv",
        "trial_balance.csv",
        "manifest.json",
    ):
        assert (out_dir / fname).is_file(), fname

    # Row counts reflect what we seeded.
    assert manifest.row_counts["account"] == 2
    assert manifest.row_counts["journal_entry"] == 1
    assert manifest.row_counts["journal_line"] == 2

    # The journal_line CSV actually contains the posted legs.
    with (out_dir / "journal_line.csv").open() as fh:
        line_rows = list(csv.DictReader(fh))
    assert len(line_rows) == 2
    debits = {r["account_id"]: r["debit"] for r in line_rows}
    assert debits[str(bank.id)] == "100.000000"

    # Balanced snapshot, and the checksum matches the file on disk.
    assert manifest.balanced is True
    assert manifest.total_debits == manifest.total_credits == Decimal("100.00")
    digest = hashlib.sha256((out_dir / "account.csv").read_bytes()).hexdigest()
    assert manifest.checksums["account.csv"] == digest

    meta = json.loads((out_dir / "manifest.json").read_text())
    assert meta["trial_balance"]["balanced"] is True


@pytest.mark.asyncio
async def test_archive_endpoint_creates_and_lists(
    client: AsyncClient, app_session: AsyncSession, tmp_path: Path
) -> None:
    token = await token_for(Role.OWNER, client, app_session)
    bank = await seed_account(app_session, code="1000", name="Bank", type="asset")
    revenue = await seed_account(app_session, code="4000", name="Sales", type="revenue")
    # Seed a posted JE through an owner so an open period exists.
    owner = await seed_owner(app_session, email="poster@example.com")
    await _post_je(
        app_session,
        actor_user_id=owner.id,
        lines=[(bank.id, "50.00", "0"), (revenue.id, "0", "50.00")],
    )
    await SettingsService.set(
        "quickbooks.archive_dir", str(tmp_path), session=app_session, actor_user_id=None
    )
    await app_session.commit()

    r = await client.post(
        "/api/v1/admin/quickbooks/decommission/archive",
        json={},
        headers=auth_header(token),
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["balanced"] is True
    assert body["row_counts"]["journal_entry"] == 1
    # Artifacts landed under the configured archive_dir.
    assert str(tmp_path) in body["artifact_dir"]
    assert Path(body["artifact_dir"], "manifest.json").is_file()

    r2 = await client.get(
        "/api/v1/admin/quickbooks/decommission/archive", headers=auth_header(token)
    )
    assert r2.status_code == 200, r2.text
    assert len(r2.json()["items"]) == 1


@pytest.mark.asyncio
async def test_archive_endpoint_requires_owner(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    token = await token_for(Role.BOOKKEEPER, client, app_session)
    r = await client.post(
        "/api/v1/admin/quickbooks/decommission/archive",
        json={},
        headers=auth_header(token),
    )
    assert r.status_code == 403, r.text
