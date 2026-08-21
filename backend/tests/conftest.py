import asyncio
import os

import pytest
import pytest_asyncio

TEST_DB = os.environ.get("SPOOL_TEST_DATABASE_URL", "postgresql+asyncpg://spool:spool@localhost:5433/spooltrackr_test")
os.environ["SPOOL_DATABASE_URL"] = TEST_DB
os.environ["SPOOL_PRINTER_MODE"] = "mock"


async def _ensure_test_db():
    import asyncpg

    admin = TEST_DB.replace("+asyncpg", "").rsplit("/", 1)[0] + "/postgres"
    conn = await asyncpg.connect(admin)
    try:
        exists = await conn.fetchval("select 1 from pg_database where datname='spooltrackr_test'")
        if not exists:
            await conn.execute("create database spooltrackr_test")
    finally:
        await conn.close()


@pytest_asyncio.fixture()
async def client():
    await _ensure_test_db()
    from httpx import ASGITransport, AsyncClient

    from app.db import Base, engine
    from app.main import app

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            yield c
