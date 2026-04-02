from click.testing import CliRunner

from vaalikone.cli.main import cli


def test_ingest_eduskunta_help():
    runner = CliRunner()
    result = runner.invoke(cli, ["ingest", "--help"])
    assert result.exit_code == 0
    assert "ingest" in result.output.lower()
