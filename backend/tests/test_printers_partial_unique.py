"""Postgres integration test: the partial unique index
``ux_printer_slug_active`` rejects two active rows with the same slug
at the DB level, while allowing archived rows to share slugs.
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from app.models import Base
from app.models.printer import Printer, PrinterType
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture
async def pg_engine(postgres_url: str):
    eng = create_async_engine(postgres_url, future=True)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def pg_session_factory(pg_engine):
    return async_sessionmaker(pg_engine, expire_on_commit=False)


@pytest.mark.asyncio
async def test_two_active_same_slug_rejected_by_db(pg_session_factory) -> None:
    async with pg_session_factory() as s:
        s.add(
            Printer(
                id=uuid.uuid4(),
                name="One",
                slug="voron",
                printer_type=PrinterType.VORON_V2_4,
                is_archived=False,
            )
        )
        await s.commit()

    async with pg_session_factory() as s:
        s.add(
            Printer(
                id=uuid.uuid4(),
                name="Two",
                slug="voron",
                printer_type=PrinterType.OTHER,
                is_archived=False,
            )
        )
        with pytest.raises(IntegrityError):
            await s.commit()


@pytest.mark.asyncio
async def test_two_archived_same_slug_allowed(pg_session_factory) -> None:
    async with pg_session_factory() as s:
        s.add_all(
            [
                Printer(
                    id=uuid.uuid4(),
                    name="Old A",
                    slug="prn",
                    printer_type=PrinterType.OTHER,
                    is_archived=True,
                ),
                Printer(
                    id=uuid.uuid4(),
                    name="Old B",
                    slug="prn",
                    printer_type=PrinterType.OTHER,
                    is_archived=True,
                ),
                Printer(
                    id=uuid.uuid4(),
                    name="Current",
                    slug="prn",
                    printer_type=PrinterType.OTHER,
                    is_archived=False,
                ),
            ]
        )
        await s.commit()
