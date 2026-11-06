import asyncio
import os

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import Settings
from app.core.db import make_sessionmaker
from app.models import Base


@pytest.fixture(autouse=True)
def _clean_settings_env(monkeypatch):
    """Keep the shell environment from leaking into Settings in tests."""
    for name in Settings.model_fields:
        monkeypatch.delenv(name.upper(), raising=False)


TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://lifeledger:lifeledger@localhost:5432/lifeledger_test",
)


@pytest.fixture(scope="session")
def _schema():
    """Create a fresh schema once per test session (sync, so it owns its own loop)."""

    async def build() -> None:
        engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)
        await engine.dispose()

    asyncio.run(build())


@pytest.fixture
async def engine(_schema):
    eng = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
    names = ", ".join(f'"{t.name}"' for t in Base.metadata.sorted_tables)
    async with eng.begin() as conn:
        await conn.execute(text(f"TRUNCATE {names} RESTART IDENTITY CASCADE"))
    yield eng
    await eng.dispose()


@pytest.fixture
def sessionmaker(engine):
    return make_sessionmaker(engine)


@pytest.fixture
async def session(sessionmaker):
    async with sessionmaker() as s:
        yield s
