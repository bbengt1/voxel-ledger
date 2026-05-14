"""Pytest fixtures.

Default DB for unit tests is in-memory SQLite via aiosqlite — fast, no
external deps. Integration tests can opt into Postgres via the
`postgres_url` fixture, which uses testcontainers when Docker is available
and skips otherwise.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Iterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Set env BEFORE the app imports anything that reads Settings.
os.environ.setdefault("TESTING", "true")
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-not-a-real-secret-xx")

from app.core import db as db_module
from app.core.settings import Settings
from app.main import create_app


@pytest.fixture
def settings() -> Settings:
    return Settings(
        database_url="sqlite+aiosqlite:///:memory:",
        jwt_secret_key="test-secret-key-not-a-real-secret-xx",
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
    """HTTP client bound to a freshly constructed app."""
    app = create_app(settings=settings)
    transport = ASGITransport(app=app)
    async with (
        AsyncClient(transport=transport, base_url="http://testserver") as ac,
        app.router.lifespan_context(app),
    ):
        yield ac
    await db_module.dispose_engine()


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
