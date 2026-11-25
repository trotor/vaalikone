from collections.abc import AsyncGenerator

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from vaalikone.db.engine import create_db_engine
from vaalikone.models import Base

DATABASE_URL = "sqlite+aiosqlite:///./vaalikone_test.db"


@pytest.fixture(scope="session")
async def engine():
    import os

    if os.path.exists("./vaalikone_test.db"):
        os.remove("./vaalikone_test.db")
    engine = create_db_engine(DATABASE_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture
async def db_session(engine) -> AsyncGenerator[AsyncSession, None]:
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        yield session
        await session.rollback()
