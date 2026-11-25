import pytest
from httpx import ASGITransport, AsyncClient

from vaalikone.api.app import app
from vaalikone.api.deps import get_db
from vaalikone.models.candidate import Candidate
from vaalikone.models.election import Election, ElectionType
from vaalikone.models.party import Party


@pytest.fixture
async def client(db_session):
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


async def _seed_election(db_session):
    party = Party(name="Testipuolue", abbreviation="XEL")
    election = Election(
        year=2023, election_type=ElectionType.EDUSKUNTAVAALIT, name="Eduskuntavaalit 2023"
    )
    db_session.add_all([party, election])
    await db_session.flush()
    db_session.add_all([
        Candidate(
            election_id=election.id, party_id=party.id, candidate_number="001",
            first_name="Matti", last_name="Meikäläinen", constituency="Helsinki",
            votes=100, elected=True,
        ),
        Candidate(
            election_id=election.id, party_id=party.id, candidate_number="002",
            first_name="Liisa", last_name="Esimerkki", constituency="Helsinki",
            votes=50, elected=False,
        ),
    ])
    await db_session.commit()
    return election.id


async def test_elections_endpoints(client, db_session):
    election_id = await _seed_election(db_session)

    r = await client.get("/api/v1/elections")
    assert r.status_code == 200
    assert any(e["year"] == 2023 for e in r.json())

    r = await client.get(f"/api/v1/elections/{election_id}/candidates")
    assert r.status_code == 200
    assert r.json()["count"] == 2

    r = await client.get(
        f"/api/v1/elections/{election_id}/candidates", params={"elected_only": True}
    )
    assert r.json()["count"] == 1
    assert r.json()["candidates"][0]["name"] == "Matti Meikäläinen"

    r = await client.get(f"/api/v1/elections/{election_id}/candidates", params={"party": "XEL"})
    assert r.json()["count"] == 2
    r = await client.get(f"/api/v1/elections/{election_id}/candidates", params={"party": "EI_OLE"})
    assert r.json()["count"] == 0

    r = await client.get(f"/api/v1/elections/{election_id}/candidates", params={"q": "meikäläinen"})
    assert r.json()["count"] == 1

    r = await client.get(f"/api/v1/elections/{election_id}/stats")
    assert r.status_code == 200
    assert r.json()["parties"][0]["party"] == "XEL"
    assert r.json()["parties"][0]["elected"] == 1


async def test_stats_includes_elections(client):
    r = await client.get("/api/v1/stats")
    assert r.status_code == 200
    assert "elections" in r.json()
    assert "candidates" in r.json()
