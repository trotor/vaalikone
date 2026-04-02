from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from vaalikone.core.database import create_session_factory


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    factory = create_session_factory()
    async with factory() as session:
        yield session
