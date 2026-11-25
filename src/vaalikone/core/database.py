from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from vaalikone.core.config import get_settings
from vaalikone.db.engine import create_db_engine


def create_engine():
    settings = get_settings()
    return create_db_engine(settings.DATABASE_URL, echo=False)


def create_session_factory(engine=None):
    if engine is None:
        engine = create_engine()
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db_session():
    factory = create_session_factory()
    async with factory() as session:
        yield session
