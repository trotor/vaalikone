import asyncio

import click
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from vaalikone.core.config import get_settings
from vaalikone.query.hybrid_search import text_search


async def _search(query_text: str, party: str | None, limit: int):
    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        results = await text_search(session, query_text, limit=limit, party_filter=party)

        if not results:
            click.echo("Ei tuloksia.")
            return

        for i, r in enumerate(results, 1):
            click.echo(f"\n{'='*60}")
            click.echo(f"#{i} [{r['party'] or '?'}] {r['title']}")
            click.echo(f"Tyyppi: {r['content_type'] or '-'}  |  Relevanssi: {r['relevance']:.4f}")
            click.echo("-"*60)
            # Clean up snippet HTML
            snippet = r['snippet'].replace('<b>', '**').replace('</b>', '**')
            click.echo(snippet)

        click.echo(f"\n{len(results)} tulosta.")

    await engine.dispose()


@click.command()
@click.argument("query")
@click.option("--party", default=None, help="Filter by party (e.g. SDP)")
@click.option("--limit", default=5, help="Max results")
def search(query: str, party: str | None, limit: int):
    """Search documents with full-text search."""
    asyncio.run(_search(query, party, limit))
