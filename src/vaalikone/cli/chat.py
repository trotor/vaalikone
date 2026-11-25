import asyncio

import click
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from vaalikone.core.config import get_settings
from vaalikone.query.pipeline import query as run_query


async def _chat(question: str, party: str | None, model: str | None):
    settings = get_settings()
    llm_model = model or settings.DEFAULT_LLM_MODEL
    engine = create_async_engine(settings.DATABASE_URL)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        click.echo(f"Kysytään ({llm_model})...\n")
        result = await run_query(
            session, question, model=llm_model, party_filter=party
        )

        click.echo(result["answer"])

        if result["sources"]:
            click.echo("\nLähteet:")
            for s in result["sources"]:
                click.echo(f"  - [{s['party'] or '?'}] {s['title']}")

    await engine.dispose()


@click.command()
@click.argument("question")
@click.option("--party", default=None, help="Filter by party (e.g. SDP)")
@click.option("--model", default=None, help="LLM model to use")
def chat(question: str, party: str | None, model: str | None):
    """Ask a question about Finnish politics using AI."""
    asyncio.run(_chat(question, party, model))
