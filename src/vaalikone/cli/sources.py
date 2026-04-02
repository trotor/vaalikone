import asyncio

import click
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from vaalikone.core.config import get_settings
from vaalikone.models.party import Party
from vaalikone.models.source import Source


async def _list_sources(party_filter: str | None):
    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        query = select(Source)
        if party_filter:
            query = (
                query.join(Party, Source.party_id == Party.id)
                .where(Party.abbreviation == party_filter.upper())
            )
        result = await session.execute(query)
        sources = result.scalars().all()

        if not sources:
            click.echo("No sources found.")
            return

        click.echo(f"{'ID':<38} {'Type':<14} {'Status':<10} {'Title'}")
        click.echo("-" * 100)
        for s in sources:
            click.echo(
                f"{str(s.id):<38} {s.source_type.value:<14} {s.status.value:<10} {s.title or s.url or '-'}"
            )
        click.echo(f"\nTotal: {len(sources)} sources")

    await engine.dispose()


async def _show_stats():
    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        result = await session.execute(
            select(Source.source_type, Source.status, func.count(Source.id))
            .group_by(Source.source_type, Source.status)
        )
        rows = result.all()

        if not rows:
            click.echo("No sources in database.")
            return

        click.echo(f"{'Type':<14} {'Status':<10} {'Count'}")
        click.echo("-" * 40)
        total = 0
        for source_type, status, count in rows:
            click.echo(f"{source_type.value:<14} {status.value:<10} {count}")
            total += count
        click.echo(f"\nTotal: {total} sources")

    await engine.dispose()


@click.group()
def sources():
    """Manage and inspect data sources."""
    pass


@sources.command(name="list")
@click.option("--party", default=None, help="Filter by party abbreviation (e.g. SDP).")
def list_sources(party: str | None):
    """List all indexed sources."""
    asyncio.run(_list_sources(party))


@sources.command()
def stats():
    """Show source statistics."""
    asyncio.run(_show_stats())
