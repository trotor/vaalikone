import pytest
from httpx import ASGITransport, AsyncClient

from vaalikone.api.app import app
from vaalikone.api.deps import get_db
from vaalikone.models.document import ContentType, Document
from vaalikone.models.party import Party
from vaalikone.models.source import Source, SourceStatus, SourceType


@pytest.fixture
async def client(db_session):
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    p1 = Party(name="Puolue A", abbreviation="PA")
    p2 = Party(name="Puolue B", abbreviation="PB")
    db_session.add_all([p1, p2])
    await db_session.flush()
    for party, text in [
        (p1, "Puolue A kannattaa metsätaloutta ja puurakentamista aktiivisesti."),
        (p2, "Puolue B haluaa suojella metsiä ja vähentää hakkuita."),
    ]:
        src = Source(
            source_type=SourceType.MANUAL, url=f"https://example.com/{party.abbreviation}",
            title=f"{party.abbreviation} ohjelma", status=SourceStatus.INDEXED,
        )
        db_session.add(src)
        await db_session.flush()
        db_session.add(
            Document(
                source_id=src.id, party_id=party.id, title=f"{party.abbreviation} ohjelma",
                content_text=text, content_type=ContentType.VAALIOHJELMA, language="fi",
            )
        )
    await db_session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


async def test_compare_groups_by_party(client):
    r = await client.get("/api/v1/compare", params={"q": "metsä"})
    assert r.status_code == 200
    data = r.json()
    assert data["party_count"] >= 2
    parties = {p for p in data["parties"]}
    assert {"PA", "PB"} <= parties
    for items in data["parties"].values():
        for item in items:
            assert "snippet" in item and "title" in item and "relevance" in item
