import click

from vaalikone.cli.seed import seed
from vaalikone.cli.ingest import ingest
from vaalikone.cli.sources import sources
from vaalikone.cli.stats import stats
from vaalikone.cli.search import search
from vaalikone.cli.chat import chat


@click.group()
def cli():
    """Vaalikone — Suomen poliittisen datan työkalu."""
    pass


cli.add_command(seed)
cli.add_command(ingest)
cli.add_command(sources)
cli.add_command(stats)
cli.add_command(search)
cli.add_command(chat)


if __name__ == "__main__":
    cli()
