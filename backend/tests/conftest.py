"""Pytest fixtures.

Default DB for unit tests is in-memory SQLite via aiosqlite — fast, no
external deps. Integration tests can opt into Postgres via the
`postgres_url` fixture, which uses testcontainers when Docker is available
and skips otherwise.
"""

from __future__ import annotations

import os
import sys
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

# Make the repo-root `scripts/` package importable for tests, and set env
# BEFORE anything imports Settings.
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

os.environ.setdefault("TESTING", "true")
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-not-a-real-secret-xx")
os.environ.setdefault("BCRYPT_ROUNDS", "4")

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from app.core import db as db_module  # noqa: E402
from app.core.settings import Settings  # noqa: E402
from app.main import create_app  # noqa: E402
from app.models import Base  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


@pytest.fixture(autouse=True)
def _reset_login_limiter() -> Iterator[None]:
    """Login rate limiter is module-level state; clear between tests."""
    from app.api.v1.auth import reset_login_limiter

    reset_login_limiter()
    yield
    reset_login_limiter()


@pytest.fixture
def settings() -> Settings:
    return Settings(
        database_url="sqlite+aiosqlite:///:memory:",
        jwt_secret_key="test-secret-key-not-a-real-secret-xx",
        bcrypt_rounds=4,
        environment="test",
        testing=True,
    )


@pytest_asyncio.fixture
async def engine(settings: Settings) -> AsyncIterator[object]:
    eng = create_async_engine(settings.database_url, future=True)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session(engine) -> AsyncIterator[AsyncSession]:
    """Per-test session. SQLite in-memory is naturally test-isolated."""
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with factory() as s:
        yield s


@pytest_asyncio.fixture
async def client(settings: Settings) -> AsyncIterator[AsyncClient]:
    """HTTP client bound to a freshly constructed app.

    Creates the schema after lifespan startup so test endpoints can read
    and write through the same in-memory SQLite the app holds.
    """
    app = create_app(settings=settings)
    transport = ASGITransport(app=app)
    async with (
        AsyncClient(transport=transport, base_url="http://testserver") as ac,
        app.router.lifespan_context(app),
    ):
        engine = db_module.get_engine()
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        yield ac
    await db_module.dispose_engine()


@pytest_asyncio.fixture
async def app_session(client: AsyncClient) -> AsyncIterator[AsyncSession]:
    """A session bound to the *running app's* engine.

    Use this when a test needs to seed users that the HTTP-driven endpoints
    will subsequently see. The plain `session` fixture above is isolated
    and won't share state with the in-process app.
    """
    factory = db_module._session_factory
    assert factory is not None
    async with factory() as s:
        yield s


@pytest_asyncio.fixture
async def workshop_location(app_session: AsyncSession):
    """An active workshop-kind inventory location pre-seeded against the
    running app's DB.

    Many tests need *some* workshop location to exist because:

    - The Phase 3.2 material-receipt refactor (#56) writes an
      `inventory_transaction` row alongside the receipt. The fallback for
      the target location is "lowest-code active workshop" unless
      `inventory.default_receiving_location_id` is set.
    - Several inventory-transaction tests need a destination location at
      all.

    Use this fixture in any test that hits the HTTP layer for
    receipts/transactions. Service-layer tests that need multiple
    locations (transfers, etc.) should seed their own.

    See `agents.md` "Test-fixture patterns" and issue #57.
    """
    from app.services import inventory_locations as locations_service

    loc = await locations_service.create(
        app_session,
        name="Test workshop",
        code="WSB",
        kind="workshop",
        actor_user_id=None,
    )
    await app_session.commit()
    return loc


@pytest_asyncio.fixture
async def accounting_period_today(app_session: AsyncSession):
    """An open accounting period whose date range contains today.

    The Phase 4.3 period-gating check (#66) runs before any other
    validation in ``JournalEntriesService.post(...)``. Any test that
    posts a journal entry needs an open period covering the entry's
    ``posted_at`` date or every POST will 400 with
    ``posted_at falls outside any defined accounting period``.

    The window is 60 days centred on today, named ``test-period``.

    See `agents.md` "Test-fixture patterns" and issue #57.
    """
    from datetime import UTC, datetime, timedelta

    from app.services import accounting_periods as periods_service

    today = datetime.now(UTC).date()
    period = await periods_service.create(
        name="test-period",
        start_date=today - timedelta(days=30),
        end_date=today + timedelta(days=30),
        session=app_session,
        actor_user_id=None,
    )
    await app_session.commit()
    return period


@pytest.fixture
def postgres_url() -> Iterator[str]:
    """Opt-in Postgres URL via testcontainers; skip when Docker missing."""
    try:
        from testcontainers.postgres import PostgresContainer
    except ImportError:
        pytest.skip("testcontainers not installed")

    try:
        with PostgresContainer("postgres:16-alpine") as pg:
            raw = pg.get_connection_url()
            # testcontainers returns a psycopg URL; switch to asyncpg.
            url = raw.replace("postgresql+psycopg2", "postgresql+asyncpg").replace(
                "postgresql://", "postgresql+asyncpg://"
            )
            yield url
    except Exception as exc:
        pytest.skip(f"Postgres container unavailable: {exc}")
