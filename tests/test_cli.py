from click.testing import CliRunner

from vaalikone.cli.main import cli


def test_cli_help():
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "Vaalikone" in result.output


def test_cli_seed_parties_help():
    runner = CliRunner()
    result = runner.invoke(cli, ["seed", "parties", "--help"])
    assert result.exit_code == 0
    assert "parties.yaml" in result.output or "puolueet" in result.output.lower()
