import asyncio

import click
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

from vaalikone.core.config import get_settings
from vaalikone.db.engine import create_db_engine
from vaalikone.models.document import Document
from vaalikone.models.party import Party


async def _list_documents(party_filter: str | None):
    settings = get_settings()
    engine = create_db_engine(settings.DATABASE_URL)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        if party_filter:
            query = (
                select(Document)
                .join(Party, Document.party_id == Party.id)
                .where(Party.abbreviation == party_filter.upper())
                .order_by(Document.title)
            )
            result = await session.execute(query)
            docs = result.scalars().all()

            if not docs:
                click.echo(f"No documents for {party_filter.upper()}")
                await engine.dispose()
                return

            click.echo(f"\nDocuments for {party_filter.upper()}:\n")
            for d in docs:
                length = len(d.content_text) if d.content_text else 0
                click.echo(f"  {d.title[:60]:<62} {length:>8,} chars")
            click.echo(f"\nTotal: {len(docs)} documents")
        else:
            # Show summary per party
            query = (
                select(
                    Party.abbreviation,
                    Party.name,
                    func.count(Document.id).label("doc_count"),
                    func.sum(func.length(Document.content_text)).label("total_chars"),
                )
                .outerjoin(Document, Document.party_id == Party.id)
                .group_by(Party.id)
                .order_by(Party.abbreviation)
            )
            result = await session.execute(query)
            rows = result.all()

            click.echo(f"\n{'Puolue':<8} {'Nimi':<45} {'Docs':>5} {'Merkkejä':>12}")
            click.echo("-" * 75)
            for abbr, name, count, chars in rows:
                click.echo(f"{abbr:<8} {name[:44]:<45} {count:>5} {chars or 0:>12,}")
            click.echo()

    await engine.dispose()


@click.command(name="documents")
@click.option("--party", default=None, help="Show documents for specific party")
def documents(party: str | None):
    """List documents per party."""
    asyncio.run(_list_documents(party))
