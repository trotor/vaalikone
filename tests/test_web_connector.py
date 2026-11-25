import pytest
from click.testing import CliRunner

from vaalikone.cli.main import cli
from vaalikone.ingest.connectors.web import fetch_and_extract


@pytest.mark.asyncio
async def test_fetch_and_extract():
    result = await fetch_and_extract("https://www.liberaalipuolue.fi/puolueohjelma/")
    assert result is not None
    assert len(result["text"]) > 100
    assert result["url"] == "https://www.liberaalipuolue.fi/puolueohjelma/"


def test_ingest_url_help():
    runner = CliRunner()
    result = runner.invoke(cli, ["ingest", "url", "--help"])
    assert result.exit_code == 0
