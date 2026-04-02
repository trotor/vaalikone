import click

from vaalikone.cli.seed import seed
from vaalikone.cli.ingest import ingest


@click.group()
def cli():
    """Vaalikone — Suomen poliittisen datan työkalu."""
    pass


cli.add_command(seed)
cli.add_command(ingest)


if __name__ == "__main__":
    cli()
