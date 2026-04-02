import asyncio

import click
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from vaalikone.core.config import get_settings
from vaalikone.models.party import Party
from vaalikone.models.representative import Representative
from vaalikone.models.source import Source
from vaalikone.models.document import Document
from vaalikone.models.embedding import Embedding
from vaalikone.models.vote import Vote


async def _show_stats():
    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        click.echo("\n📊 Vaalikone Database Stats\n")
        total = 0
        for name, model in [
            ("Puolueet", Party),
            ("Kansanedustajat", Representative),
            ("Lähteet", Source),
            ("Dokumentit", Document),
            ("Embeddings", Embedding),
            ("Äänestykset", Vote),
        ]:
            result = await session.execute(select(func.count()).select_from(model))
            count = result.scalar()
            total += count
            click.echo(f"  {name:<20} {count:>8}")

        click.echo(f"\n  {'Yhteensä':<20} {total:>8}\n")

    await engine.dispose()


@click.command()
def stats():
    """Show database statistics."""
    asyncio.run(_show_stats())
