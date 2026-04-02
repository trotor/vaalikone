import click

from vaalikone.cli.seed import seed


@click.group()
def cli():
    """Vaalikone — Suomen poliittisen datan työkalu."""
    pass


cli.add_command(seed)


if __name__ == "__main__":
    cli()
