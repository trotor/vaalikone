"""
End-to-end smoke test: verify API endpoints return real data.
Requires running PostgreSQL (docker compose up postgres).
"""
import pytest
from httpx import ASGITransport, AsyncClient

from vaalikone.api.app import app


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def test_full_flow(client):
    """Health check works and API returns lists."""
    health = await client.get("/health")
    assert health.status_code == 200

    parties = await client.get("/api/v1/parties")
    assert parties.status_code == 200
    assert isinstance(parties.json(), list)

    reps = await client.get("/api/v1/representatives")
    assert reps.status_code == 200

    sources = await client.get("/api/v1/sources")
    assert sources.status_code == 200
