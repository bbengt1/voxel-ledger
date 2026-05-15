"""Journal-entry / journal-line immutability triggers (Phase 4.2).

These are PG-only — the trigger function uses plpgsql. SQLite has no
triggers in this codebase. Skips cleanly when Docker is unreachable.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
import pytest_asyncio
from app.models import Base
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

pytestmark = pytest.mark.integration


JE_TRIGGER_FN = """
CREATE OR REPLACE FUNCTION journal_entry_immutability_check()
RETURNS trigger AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'journal_entry is append-only; deletion is not allowed';
  END IF;
  IF NOT (
    NEW.id IS NOT DISTINCT FROM OLD.id
    AND NEW.entry_number IS NOT DISTINCT FROM OLD.entry_number
    AND NEW.posted_at IS NOT DISTINCT FROM OLD.posted_at
    AND NEW.period_id IS NOT DISTINCT FROM OLD.period_id
    AND NEW.description IS NOT DISTINCT FROM OLD.description
    AND NEW.source_event_id IS NOT DISTINCT FROM OLD.source_event_id
    AND NEW.actor_user_id IS NOT DISTINCT FROM OLD.actor_user_id
    AND NEW.reversal_of_entry_id IS NOT DISTINCT FROM OLD.reversal_of_entry_id
    AND OLD.is_reversed = false
    AND NEW.is_reversed = true
  ) THEN
    RAISE EXCEPTION 'journal_entry is append-only; only is_reversed may flip false->true';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql
"""

JL_TRIGGER_FN = """
CREATE OR REPLACE FUNCTION journal_line_immutability_check()
RETURNS trigger AS $$
BEGIN
  RAISE EXCEPTION 'journal_line is append-only (op=%, line_id=%)', TG_OP, COALESCE(OLD.id, NEW.id);
END;
$$ LANGUAGE plpgsql
"""


@pytest_asyncio.fixture
async def pg_factory(postgres_url: str):
    eng = create_async_engine(postgres_url, future=True)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Mirror the migration's PG-only DDL.
        await conn.execute(text(JE_TRIGGER_FN))
        await conn.execute(
            text(
                "CREATE TRIGGER journal_entry_immutability_trg "
                "BEFORE UPDATE OR DELETE ON journal_entry "
                "FOR EACH ROW EXECUTE FUNCTION journal_entry_immutability_check()"
            )
        )
        await conn.execute(text(JL_TRIGGER_FN))
        await conn.execute(
            text(
                "CREATE TRIGGER journal_line_immutability_trg "
                "BEFORE UPDATE OR DELETE ON journal_line "
                "FOR EACH ROW EXECUTE FUNCTION journal_line_immutability_check()"
            )
        )
    factory = async_sessionmaker(eng, expire_on_commit=False)
    yield factory
    await eng.dispose()


async def _seed_user_and_entry(factory):
    """Insert one user + one entry + one line. Returns (user_id, entry_id, line_id)."""
    user_id = uuid.uuid4()
    entry_id = uuid.uuid4()
    line_id = uuid.uuid4()
    account_id = uuid.uuid4()
    async with factory() as s:
        await s.execute(
            text(
                'INSERT INTO "user" (id, email, password_hash, full_name, role, is_active,'
                " created_at, updated_at)"
                " VALUES (:id, :em, 'hash', 'X', 'owner', true, now(), now())"
            ),
            {"id": user_id, "em": f"x-{user_id}@example.com"},
        )
        await s.execute(
            text(
                "INSERT INTO account (id, code, name, type, is_archived, created_at, updated_at) "
                "VALUES (:id, :code, 'X', 'asset', false, now(), now())"
            ),
            {"id": account_id, "code": f"C-{account_id}"},
        )
        await s.execute(
            text(
                "INSERT INTO journal_entry (id, entry_number, posted_at, description, "
                "actor_user_id, is_reversed, created_at) "
                "VALUES (:id, :n, now(), 'd', :uid, false, now())"
            ),
            {"id": entry_id, "n": f"JE-T-{entry_id}", "uid": user_id},
        )
        await s.execute(
            text(
                "INSERT INTO journal_line (id, entry_id, account_id, debit, credit, line_number) "
                "VALUES (:id, :eid, :aid, :d, :c, 1)"
            ),
            {
                "id": line_id,
                "eid": entry_id,
                "aid": account_id,
                "d": Decimal("10"),
                "c": Decimal("0"),
            },
        )
        await s.commit()
    return entry_id, line_id


@pytest.mark.asyncio
async def test_journal_line_update_raises(pg_factory) -> None:
    _, line_id = await _seed_user_and_entry(pg_factory)
    async with pg_factory() as s:
        with pytest.raises(DBAPIError):
            await s.execute(
                text("UPDATE journal_line SET memo = 'changed' WHERE id = :id"),
                {"id": line_id},
            )
            await s.commit()


@pytest.mark.asyncio
async def test_journal_line_delete_raises(pg_factory) -> None:
    _, line_id = await _seed_user_and_entry(pg_factory)
    async with pg_factory() as s:
        with pytest.raises(DBAPIError):
            await s.execute(
                text("DELETE FROM journal_line WHERE id = :id"),
                {"id": line_id},
            )
            await s.commit()


@pytest.mark.asyncio
async def test_journal_entry_arbitrary_update_raises(pg_factory) -> None:
    entry_id, _ = await _seed_user_and_entry(pg_factory)
    async with pg_factory() as s:
        with pytest.raises(DBAPIError):
            await s.execute(
                text("UPDATE journal_entry SET description = 'tampered' WHERE id = :id"),
                {"id": entry_id},
            )
            await s.commit()


@pytest.mark.asyncio
async def test_journal_entry_delete_raises(pg_factory) -> None:
    entry_id, _ = await _seed_user_and_entry(pg_factory)
    async with pg_factory() as s:
        with pytest.raises(DBAPIError):
            await s.execute(
                text("DELETE FROM journal_entry WHERE id = :id"),
                {"id": entry_id},
            )
            await s.commit()


@pytest.mark.asyncio
async def test_journal_entry_is_reversed_flip_allowed(pg_factory) -> None:
    entry_id, _ = await _seed_user_and_entry(pg_factory)
    async with pg_factory() as s:
        await s.execute(
            text("UPDATE journal_entry SET is_reversed = true WHERE id = :id"),
            {"id": entry_id},
        )
        await s.commit()
    # And flipping it back is rejected.
    async with pg_factory() as s:
        with pytest.raises(DBAPIError):
            await s.execute(
                text("UPDATE journal_entry SET is_reversed = false WHERE id = :id"),
                {"id": entry_id},
            )
            await s.commit()
