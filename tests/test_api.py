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


async def test_stats(client):
    resp = await client.get("/api/v1/stats")
    assert resp.status_code == 200
    data = resp.json()
    assert "parties" in data
    assert "representatives" in data
    assert "total_data_points" in data
    assert all(isinstance(v, int) for k, v in data.items() if k != "read_only")
    assert isinstance(data["read_only"], bool)


async def test_search_endpoint(client):
    resp = await client.get("/api/v1/search?q=verotus")
    assert resp.status_code == 200
    data = resp.json()
    assert "results" in data
    assert "count" in data


async def test_list_documents(client):
    resp = await client.get("/api/v1/documents")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


async def test_get_party_not_found(client):
    resp = await client.get("/api/v1/parties/NOTEXIST")
    assert resp.status_code == 404
