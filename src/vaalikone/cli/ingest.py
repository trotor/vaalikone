import asyncio

import click
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from vaalikone.core.config import get_settings
from vaalikone.ingest.connectors.eduskunta import EduskuntaClient
from vaalikone.ingest.connectors.pdf import fetch_and_extract_pdf
from vaalikone.ingest.connectors.web import fetch_and_extract
from vaalikone.models.document import Document, ContentType
from vaalikone.models.party import Party
from vaalikone.models.representative import Representative
from vaalikone.models.source import Source, SourceType, SourceStatus
from vaalikone.models.vote import Vote, VoteChoice


# Maps eduskunta API party abbreviations to our abbreviations
PARTY_MAP = {
    "sd": "SDP",
    "kok": "KOK",
    "ps": "PS",
    "kesk": "KESK",
    "vihr": "VIHR",
    "vas": "VAS",
    "r": "RKP",
    "kd": "KD",
    "liik": "LIIK",
    "sin": "SML",
}


def _map_vote(api_vote: str) -> VoteChoice:
    mapping = {
        "Jaa": VoteChoice.JAA,
        "Ei": VoteChoice.EI,
        "Tyhjaa": VoteChoice.TYHJA,
        "Tyhjää": VoteChoice.TYHJA,
        "Poissa": VoteChoice.POISSA,
    }
    return mapping.get(api_vote, VoteChoice.POISSA)


async def _get_session():
    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return engine, async_session


async def _find_party(session: AsyncSession, api_party: str) -> Party | None:
    abbr = PARTY_MAP.get(api_party.lower(), api_party.upper())
    result = await session.execute(select(Party).where(Party.abbreviation == abbr))
    return result.scalar_one_or_none()


async def _ingest_representatives():
    client = EduskuntaClient()
    click.echo("Fetching representatives from eduskunta API...")
    reps = await client.fetch_representatives()
    click.echo(f"Fetched {len(reps)} representatives from API.")

    engine, async_session = await _get_session()

    async with async_session() as session:
        # Register source
        source = Source(
            source_type=SourceType.API,
            url="https://avoindata.eduskunta.fi/api/v1/tables/MemberOfParliament/rows",
            title="Eduskunta - Kansanedustajat",
            status=SourceStatus.INDEXED,
        )
        session.add(source)

        added = 0
        skipped = 0
        with session.no_autoflush:
            for rep_data in reps:
                person_id = rep_data.get("personId", "")
                first_name = rep_data.get("firstname", "")
                last_name = rep_data.get("lastname", "")

                if not first_name or not last_name:
                    skipped += 1
                    continue

                # Check if already exists
                result = await session.execute(
                    select(Representative).where(
                        Representative.first_name == first_name,
                        Representative.last_name == last_name,
                    )
                )
                if result.scalar_one_or_none():
                    skipped += 1
                    continue

                party = await _find_party(session, rep_data.get("party", ""))

                representative = Representative(
                    first_name=first_name,
                    last_name=last_name,
                    party_id=party.id if party else None,
                    social_media={"eduskunta_person_id": person_id},
                )
                session.add(representative)
                added += 1

        await session.commit()
        click.echo(f"Added {added} representatives, skipped {skipped}.")

    await engine.dispose()


async def _ingest_votes(max_pages: int | None = None):
    client = EduskuntaClient()
    click.echo("Fetching votes from eduskunta API...")
    votes = await client.fetch_votes(max_pages=max_pages)
    click.echo(f"Fetched {len(votes)} vote records from API.")

    engine, async_session = await _get_session()

    async with async_session() as session:
        source = Source(
            source_type=SourceType.API,
            url="https://avoindata.eduskunta.fi/api/v1/tables/SaliDBAanestysEdustaja/rows",
            title="Eduskunta - Äänestykset",
            status=SourceStatus.INDEXED,
        )
        session.add(source)

        added = 0
        skipped = 0
        with session.no_autoflush:
            for vote_data in votes:
                first_name = vote_data.get("EdustajaEtunimi", "")
                last_name = vote_data.get("EdustajaSukunimi", "")

                result = await session.execute(
                    select(Representative).where(
                        Representative.first_name == first_name,
                        Representative.last_name == last_name,
                    ).limit(1)
                )
                rep = result.scalar_one_or_none()
                if not rep:
                    skipped += 1
                    continue

                vote = Vote(
                    representative_id=rep.id,
                    session=vote_data.get("IstuntoVPVuosi", ""),
                    subject=vote_data.get("AanestysId", ""),
                    vote=_map_vote(vote_data.get("EdustajaAanestys", "Poissa")),
                )
                session.add(vote)
                added += 1

        await session.commit()
        click.echo(f"Added {added} votes, skipped {skipped}.")

    await engine.dispose()


@click.group()
def ingest():
    """Ingest data from various sources."""
    pass


@ingest.command()
def representatives():
    """Fetch and store representatives from eduskunta API."""
    asyncio.run(_ingest_representatives())


@ingest.command()
@click.option("--max-pages", default=None, type=int, help="Limit number of API pages to fetch.")
def votes(max_pages: int | None):
    """Fetch and store votes from eduskunta API."""
    asyncio.run(_ingest_votes(max_pages))


async def _ingest_pdf(url: str, party_abbr: str | None = None, title_override: str | None = None):
    click.echo(f"Downloading PDF {url}...")
    content = await fetch_and_extract_pdf(url)
    if not content:
        click.echo("Failed to extract text from PDF.")
        return

    title = title_override or content["title"]
    click.echo(f"Extracted: {title} ({len(content['text'])} chars, {content['pages']} pages)")

    engine, async_session = await _get_session()
    async with async_session() as session:
        party = None
        if party_abbr:
            party = await _find_party(session, party_abbr)

        source = Source(
            source_type=SourceType.PDF,
            url=url,
            title=title,
            status=SourceStatus.INDEXED,
            party_id=party.id if party else None,
        )
        session.add(source)
        await session.flush()

        doc = Document(
            source_id=source.id,
            title=title,
            content_text=content["text"],
            content_type=ContentType.MUU,
            party_id=party.id if party else None,
            language="fi",
        )
        session.add(doc)
        await session.commit()
        click.echo(f"Stored PDF document: {title}")

    await engine.dispose()


async def _ingest_url(url: str, party_abbr: str | None = None):
    if url.lower().endswith(".pdf"):
        await _ingest_pdf(url, party_abbr)
        return

    click.echo(f"Fetching {url}...")
    content = await fetch_and_extract(url)
    if not content:
        click.echo("Failed to extract content from URL.")
        return

    click.echo(f"Extracted: {content['title']} ({len(content['text'])} chars)")

    engine, async_session = await _get_session()
    async with async_session() as session:
        # Find party if specified
        party = None
        if party_abbr:
            party = await _find_party(session, party_abbr)

        # Create source
        source = Source(
            source_type=SourceType.WEBSITE,
            url=url,
            title=content["title"],
            status=SourceStatus.INDEXED,
            party_id=party.id if party else None,
        )
        session.add(source)
        await session.flush()

        # Create document
        doc = Document(
            source_id=source.id,
            title=content["title"],
            content_text=content["text"],
            content_type=ContentType.MUU,
            party_id=party.id if party else None,
            language="fi",
        )
        session.add(doc)
        await session.commit()
        click.echo(f"Stored document: {content['title']}")

    await engine.dispose()


@ingest.command()
@click.argument("url")
@click.option("--party", default=None, help="Party abbreviation (e.g. SDP)")
def url(url: str, party: str | None):
    """Ingest content from a URL."""
    asyncio.run(_ingest_url(url, party))


@ingest.command()
@click.argument("url")
@click.option("--party", default=None, help="Party abbreviation (e.g. SDP)")
@click.option("--title", default=None, help="Override document title")
def pdf(url: str, party: str | None, title: str | None):
    """Ingest a PDF document from URL."""
    asyncio.run(_ingest_pdf(url, party, title))


@ingest.command(name="pdf-file")
@click.argument("file_path", type=click.Path(exists=True))
@click.option("--party", default=None, help="Party abbreviation")
@click.option("--title", default=None, help="Override document title")
def pdf_file(file_path: str, party: str | None, title: str | None):
    """Ingest a local PDF file."""
    from vaalikone.ingest.connectors.pdf import extract_pdf_bytes

    async def _run():
        with open(file_path, "rb") as f:
            pdf_bytes = f.read()

        content = extract_pdf_bytes(pdf_bytes, file_path)
        if not content:
            click.echo("Failed to extract text from PDF.")
            return

        doc_title = title or content["title"]
        click.echo(f"Extracted: {doc_title} ({len(content['text'])} chars, {content['pages']} pages)")

        engine, async_session = await _get_session()
        async with async_session() as session:
            party_obj = None
            if party:
                party_obj = await _find_party(session, party)

            source = Source(
                source_type=SourceType.PDF,
                url=file_path,
                title=doc_title,
                status=SourceStatus.INDEXED,
                party_id=party_obj.id if party_obj else None,
            )
            session.add(source)
            await session.flush()

            doc = Document(
                source_id=source.id,
                title=doc_title,
                content_text=content["text"],
                content_type=ContentType.MUU,
                party_id=party_obj.id if party_obj else None,
                language="fi",
            )
            session.add(doc)
            await session.commit()
            click.echo(f"Stored PDF document: {doc_title}")

        await engine.dispose()

    asyncio.run(_run())


@ingest.command()
@click.option("--model", default=None, help="Embedding model (default from config)")
@click.option("--force", is_flag=True, help="Re-embed all documents")
def embed(model: str | None, force: bool):
    """Generate embeddings for all documents."""

    async def _run():
        from vaalikone.ingest.pipeline import process_all_documents

        settings = get_settings()
        embed_model = model or settings.DEFAULT_EMBED_MODEL

        engine, async_session = await _get_session()
        async with async_session() as session:
            click.echo(f"Embedding documents with {embed_model}...")
            n_docs, n_chunks = await process_all_documents(
                session, embed_model=embed_model, force=force
            )
            click.echo(f"\nProcessed {n_docs} documents, {n_chunks} chunks total.")
        await engine.dispose()

    asyncio.run(_run())
