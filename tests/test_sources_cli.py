from click.testing import CliRunner

from vaalikone.cli.main import cli


def test_sources_list_help():
    runner = CliRunner()
    result = runner.invoke(cli, ["sources", "list", "--help"])
    assert result.exit_code == 0


def test_sources_stats_help():
    runner = CliRunner()
    result = runner.invoke(cli, ["sources", "stats", "--help"])
    assert result.exit_code == 0
