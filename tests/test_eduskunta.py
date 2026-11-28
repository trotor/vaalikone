import pytest

from vaalikone.ingest.connectors.eduskunta import EduskuntaClient

# Live avoindata.eduskunta.fi -kutsuja: ohitetaan CI:ssä (-m "not network").
pytestmark = pytest.mark.network


@pytest.fixture
def client():
    return EduskuntaClient()


async def test_fetch_table_page(client):
    """Fetch one page from MemberOfParliament table."""
    result = await client.fetch_table_page("MemberOfParliament", page=0, per_page=5)
    assert result["tableName"] == "MemberOfParliament"
    assert len(result["rowData"]) <= 5
    assert "columnNames" in result
    assert "personId" in result["columnNames"]


async def test_parse_rows(client):
    """Parse raw API response into list of dicts."""
    result = await client.fetch_table_page("MemberOfParliament", page=0, per_page=3)
    rows = client.parse_rows(result)
    assert len(rows) <= 3
    assert all("personId" in row for row in rows)
    assert all("firstname" in row for row in rows)
    assert all("lastname" in row for row in rows)


async def test_fetch_all_representatives(client):
    """Fetch a small batch of representatives and parse them."""
    reps = await client.fetch_representatives(max_pages=1, per_page=10)
    assert len(reps) > 0
    assert len(reps) <= 10
    first = reps[0]
    assert "personId" in first
    assert "firstname" in first
    assert "lastname" in first
    assert "party" in first
