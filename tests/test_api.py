import pytest
from httpx import ASGITransport, AsyncClient

from vaalikone.api.app import app


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def test_health(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


async def test_list_parties(client):
    resp = await client.get("/api/v1/parties")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


async def test_list_representatives(client):
    resp = await client.get("/api/v1/representatives")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


async def test_list_sources(client):
    resp = await client.get("/api/v1/sources")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
