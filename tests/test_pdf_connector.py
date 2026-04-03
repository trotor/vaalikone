from click.testing import CliRunner
from vaalikone.cli.main import cli


def test_ingest_pdf_help():
    runner = CliRunner()
    result = runner.invoke(cli, ["ingest", "pdf", "--help"])
    assert result.exit_code == 0
    assert "pdf" in result.output.lower()
