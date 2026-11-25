import hmac
from collections.abc import AsyncGenerator

from fastapi import Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from vaalikone.core.config import get_settings
from vaalikone.core.database import create_session_factory


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    factory = create_session_factory()
    async with factory() as session:
        yield session


async def verify_api_key(x_api_key: str | None = Header(default=None)) -> None:
    """Require a matching X-API-Key header when VAALIKONE_API_KEY is configured.

    When no key is configured (local development), all requests are allowed.
    """
    settings = get_settings()
    expected = settings.VAALIKONE_API_KEY
    if not expected:
        return
    if not x_api_key or not hmac.compare_digest(x_api_key, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key (X-API-Key)",
        )
