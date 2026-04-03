from click.testing import CliRunner

from vaalikone.cli.main import cli


def test_search_help():
    runner = CliRunner()
    result = runner.invoke(cli, ["search", "--help"])
    assert result.exit_code == 0
    assert "search" in result.output.lower()


def test_chat_help():
    runner = CliRunner()
    result = runner.invoke(cli, ["chat", "--help"])
    assert result.exit_code == 0
