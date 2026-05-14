"""scripts.seed_owner — idempotent owner bootstrap.

Uses a file-backed SQLite so the schema survives the engine.dispose() the
seed script performs in its finally block.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from app.core import db as db_module
from app.core.settings import Settings
from app.models import Base
from app.models.auth import Role, User
from app.services.auth import create_user
from sqlalchemy import func, select


async def _setup(tmp_path: Path) -> Settings:
    db_path = tmp_path / "seed.db"
    settings = Settings(
        database_url=f"sqlite+aiosqlite:///{db_path}",
        jwt_secret_key="test-secret-key-not-a-real-secret-xx",
        bcrypt_rounds=4,
        owner_email="seedme@example.com",
        owner_password="seed-pw-correct",
    )
    engine = db_module.make_engine(settings)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()
    return settings


@pytest.mark.asyncio
async def test_seed_creates_owner_on_empty_table(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    settings = await _setup(tmp_path)
    monkeypatch.setattr("scripts.seed_owner.load_settings", lambda: settings)

    from scripts.seed_owner import seed

    rc = await seed()
    assert rc == 0
    assert "owner seeded" in capsys.readouterr().out

    # Re-open to verify.
    engine = db_module.make_engine(settings)
    factory = db_module.make_session_factory(engine)
    try:
        async with factory() as s:
            users = (await s.execute(select(User))).scalars().all()
            assert len(users) == 1
            assert users[0].email == "seedme@example.com"
            assert users[0].role == Role.OWNER
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_seed_is_noop_on_populated_table(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    settings = await _setup(tmp_path)

    engine = db_module.make_engine(settings)
    factory = db_module.make_session_factory(engine)
    try:
        async with factory() as s:
            await create_user(
                s,
                email="someone@example.com",
                password="pw-correct",
                full_name="Existing",
                role=Role.VIEWER,
                bcrypt_rounds=4,
            )
            await s.commit()
    finally:
        await engine.dispose()

    monkeypatch.setattr("scripts.seed_owner.load_settings", lambda: settings)
    from scripts.seed_owner import seed

    rc = await seed()
    assert rc == 0
    out = capsys.readouterr().out
    assert "already exists" in out

    engine = db_module.make_engine(settings)
    factory = db_module.make_session_factory(engine)
    try:
        async with factory() as s:
            count = (
                await s.execute(select(func.count()).select_from(User))
            ).scalar_one()
            assert count == 1
    finally:
        await engine.dispose()
