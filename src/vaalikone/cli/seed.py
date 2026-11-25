import asyncio
from pathlib import Path

import click
import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

from vaalikone.core.config import get_settings
from vaalikone.db.engine import create_db_engine
from vaalikone.models.party import Party


async def _seed_parties(config_path: str):
    path = Path(config_path)
    if not path.exists():
        click.echo(f"Config file not found: {path}")
        return

    with open(path) as f:
        data = yaml.safe_load(f)

    settings = get_settings()
    engine = create_db_engine(settings.DATABASE_URL)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        count = 0
        for party_data in data.get("parties", []):
            result = await session.execute(
                select(Party).where(Party.abbreviation == party_data["abbreviation"])
            )
            existing = result.scalar_one_or_none()
            if existing:
                click.echo(f"  Exists: {party_data['abbreviation']}")
                continue

            party = Party(
                name=party_data["name"],
                abbreviation=party_data["abbreviation"],
                website=party_data.get("website"),
                ideology=party_data.get("ideology"),
                founded=party_data.get("founded"),
            )
            session.add(party)
            count += 1
            click.echo(f"  Added: {party_data['abbreviation']}")

        await session.commit()
        click.echo(f"\nSeeded {count} new parties.")

    await engine.dispose()


@click.group()
def seed():
    """Seed database with initial data."""
    pass


@seed.command()
@click.option(
    "--config",
    default="config/parties.yaml",
    help="Path to parties.yaml config file.",
)
def parties(config: str):
    """Seed puolueet config/parties.yaml -tiedostosta."""
    click.echo("Seeding parties...")
    asyncio.run(_seed_parties(config))
