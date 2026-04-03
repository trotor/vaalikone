"""Compare embedding model quality for Finnish political queries."""

import asyncio

import click
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from vaalikone.core.config import get_settings
from vaalikone.ingest.embedder import get_embedding
from vaalikone.models.embedding import Embedding
from vaalikone.query.hybrid_search import semantic_search


TEST_QUERIES = [
    "metsäkeskus metsäpolitiikka",
    "verotus tuloverotus",
    "maahanmuutto pakolaiset",
    "ilmastonmuutos päästöt",
    "koulutus peruskoulu",
    "sosiaaliturva perusturva",
    "ydinvoima energia",
    "NATO puolustus",
    "terveydenhuolto hoitajamitoitus",
    "työllisyys yrittäjyys",
]


async def _compare(models: list[str]):
    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        # Check available models
        result = await session.execute(
            select(Embedding.model_name, func.count(Embedding.id))
            .group_by(Embedding.model_name)
        )
        available = {row[0]: row[1] for row in result.all()}
        click.echo(f"\nEmbeddings in database:")
        for model, count in available.items():
            click.echo(f"  {model}: {count} chunks")

        active_models = [m for m in models if m in available]
        if not active_models:
            click.echo(f"\nNone of {models} found in database. Run embedding first.")
            await engine.dispose()
            return

        click.echo(f"\nComparing: {', '.join(active_models)}")
        click.echo(f"{'Query':<35} ", end="")
        for m in active_models:
            short = m.split("/")[-1] if "/" in m else m
            click.echo(f"{'[' + short + ']':<30} ", end="")
        click.echo()
        click.echo("-" * (35 + 30 * len(active_models)))

        for query_text in TEST_QUERIES:
            click.echo(f"{query_text:<35} ", end="")

            for model in active_models:
                try:
                    vec = await get_embedding(query_text, model=model)
                    results = await semantic_search(
                        session, vec, limit=3, embed_model=model
                    )
                    if results:
                        # Show top result party + similarity
                        top = results[0]
                        info = f"{top['party'] or '?'} ({top['similarity']:.3f})"
                        click.echo(f"{info:<30} ", end="")
                    else:
                        click.echo(f"{'no results':<30} ", end="")
                except Exception as e:
                    click.echo(f"{'ERROR: ' + str(e)[:20]:<30} ", end="")

            click.echo()

        # Summary: average similarity scores
        click.echo(f"\n{'Avg top similarity':<35} ", end="")
        for model in active_models:
            total_sim = 0
            count = 0
            for query_text in TEST_QUERIES:
                try:
                    vec = await get_embedding(query_text, model=model)
                    results = await semantic_search(
                        session, vec, limit=1, embed_model=model
                    )
                    if results:
                        total_sim += results[0]["similarity"]
                        count += 1
                except Exception:
                    pass
            avg = total_sim / count if count else 0
            click.echo(f"{avg:.3f}{'':<25} ", end="")
        click.echo()

    await engine.dispose()


@click.command(name="compare-embeddings")
@click.option("--models", default="text-embedding-3-small,ollama/bge-m3",
              help="Comma-separated list of embedding models to compare")
def compare_embeddings(models: str):
    """Compare embedding model quality on Finnish political queries."""
    model_list = [m.strip() for m in models.split(",")]
    asyncio.run(_compare(model_list))
