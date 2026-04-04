"""Vaalikone MCP Server — Finnish political data for AI assistants.

Usage:
    # Standalone
    python -m vaalikone.mcp.server

    # Claude Code config (~/.claude/settings.json):
    {
      "mcpServers": {
        "vaalikone": {
          "command": "python",
          "args": ["-m", "vaalikone.mcp.server"],
          "cwd": "/path/to/vaalikone"
        }
      }
    }
"""

import asyncio
import os
from contextlib import asynccontextmanager

from fastmcp import FastMCP
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Load config
from vaalikone.core.config import get_settings

settings = get_settings()
if settings.OPENAI_API_KEY:
    os.environ.setdefault("OPENAI_API_KEY", settings.OPENAI_API_KEY)

# Database setup
engine = create_async_engine(settings.DATABASE_URL)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

# Models
from vaalikone.models.party import Party
from vaalikone.models.representative import Representative
from vaalikone.models.source import Source
from vaalikone.models.document import Document
from vaalikone.models.embedding import Embedding
from vaalikone.models.vote import Vote

mcp = FastMCP(
    "Vaalikone",
    instructions=(
        "Suomen poliittisen datan tietokanta. Sisältää puolueohjelmia, varjobudjetteja, "
        "kansanedustajien tietoja ja äänestyshistoriaa kaikilta 16 puolueelta. "
        "Käytä query-työkalua kysymyksiin ja search-työkalua hakuihin."
    ),
)


@mcp.tool()
async def query(
    question: str,
    party: str | None = None,
    model: str = "gpt-5.4-nano",
) -> str:
    """Kysele suomalaisesta politiikasta tekoälyllä.

    Tekee hybrid-haun tietokannasta ja generoi vastauksen LLM:llä lähdeviitteineen.

    Args:
        question: Kysymys suomeksi (esim. "Mitä puolueet sanovat metsäkeskuksesta?")
        party: Rajaa yhteen puolueeseen (esim. "SDP", "KOK", "VIHR")
        model: LLM-malli (oletus: gpt-5.4-nano)
    """
    from vaalikone.query.pipeline import query as run_query

    async with async_session() as session:
        result = await run_query(
            session,
            question=question,
            model=model,
            party_filter=party,
            use_semantic=True,
        )

    answer = result.get("answer", "Ei vastausta.")
    sources = result.get("sources", [])
    cost = result.get("cost", 0)
    tokens = result.get("tokens", {})

    source_lines = "\n".join(
        f"  - [{s.get('party', '?')}] {s.get('title', '')} — {s.get('url', '')}"
        for s in sources
    )

    return (
        f"{answer}\n\n"
        f"Lähteet:\n{source_lines}\n\n"
        f"[{model} | {tokens.get('total', 0)} tokenia | ${cost:.4f}]"
    )


@mcp.tool()
async def search(
    query_text: str,
    party: str | None = None,
    limit: int = 5,
) -> str:
    """Hae dokumenteista tekstihaulla (ei LLM:ää, ilmainen).

    Args:
        query_text: Hakusanat (esim. "verotus", "metsäkeskus")
        party: Rajaa puolueeseen (esim. "KOK")
        limit: Tulosten maksimimäärä (1-20)
    """
    from vaalikone.query.hybrid_search import text_search

    async with async_session() as session:
        results = await text_search(
            session, query_text, limit=min(limit, 20), party_filter=party
        )

    if not results:
        return "Ei hakutuloksia."

    lines = []
    for i, r in enumerate(results, 1):
        snippet = (r.get("snippet") or "")[:300].replace("<b>", "**").replace("</b>", "**")
        lines.append(
            f"#{i} [{r.get('party', '?')}] {r.get('title', '')}\n"
            f"   URL: {r.get('source_url', '-')}\n"
            f"   {snippet}"
        )

    return "\n\n".join(lines)


@mcp.tool()
async def list_parties() -> str:
    """Listaa kaikki puolueet ja niiden dokumenttimäärät."""
    async with async_session() as session:
        result = await session.execute(
            select(
                Party.abbreviation,
                Party.name,
                Party.website,
                func.count(Document.id).label("docs"),
            )
            .outerjoin(Document, Document.party_id == Party.id)
            .group_by(Party.id)
            .order_by(Party.abbreviation)
        )
        rows = result.all()

    lines = [f"{'Lyhenne':<8} {'Nimi':<45} {'Docs':>5} {'Sivu'}"]
    lines.append("-" * 80)
    for abbr, name, website, docs in rows:
        lines.append(f"{abbr:<8} {name[:44]:<45} {docs:>5} {website or '-'}")

    return "\n".join(lines)


@mcp.tool()
async def get_party(abbreviation: str) -> str:
    """Hae puolueen tiedot ja tilastot.

    Args:
        abbreviation: Puolueen lyhenne (esim. "SDP", "KOK", "VIHR")
    """
    async with async_session() as session:
        result = await session.execute(
            select(Party).where(Party.abbreviation == abbreviation.upper())
        )
        party = result.scalar_one_or_none()
        if not party:
            return f"Puoluetta '{abbreviation}' ei löydy."

        doc_count = (
            await session.execute(
                select(func.count()).select_from(Document).where(Document.party_id == party.id)
            )
        ).scalar()

        rep_count = (
            await session.execute(
                select(func.count())
                .select_from(Representative)
                .where(Representative.party_id == party.id)
            )
        ).scalar()

    return (
        f"{party.name} ({party.abbreviation})\n"
        f"Perustettu: {party.founded or '-'}\n"
        f"Aate: {party.ideology or '-'}\n"
        f"Sivusto: {party.website or '-'}\n"
        f"Dokumentteja: {doc_count}\n"
        f"Kansanedustajia: {rep_count}"
    )


@mcp.tool()
async def stats() -> str:
    """Näytä tietokannan tilastot."""
    async with async_session() as session:
        counts = {}
        for name, model in [
            ("Puolueet", Party),
            ("Kansanedustajat", Representative),
            ("Lähteet", Source),
            ("Dokumentit", Document),
            ("Embeddings", Embedding),
            ("Äänestykset", Vote),
        ]:
            result = await session.execute(select(func.count()).select_from(model))
            counts[name] = result.scalar()

    total = sum(counts.values())
    lines = ["Vaalikone — tietokannan tilastot", ""]
    for name, count in counts.items():
        lines.append(f"  {name:<20} {count:>8,}")
    lines.append(f"\n  {'Yhteensä':<20} {total:>8,}")

    return "\n".join(lines)


@mcp.tool()
async def ingest_url(
    url: str,
    party: str | None = None,
) -> str:
    """Indeksoi web-sivu tai PDF tietokantaan.

    Args:
        url: Web-sivun tai PDF:n URL
        party: Puolueen lyhenne (esim. "SDP")
    """
    from vaalikone.ingest.connectors.web import fetch_and_extract
    from vaalikone.ingest.connectors.pdf import fetch_and_extract_pdf
    from vaalikone.models.source import SourceType, SourceStatus

    # Detect PDF
    if url.lower().endswith(".pdf"):
        content = await fetch_and_extract_pdf(url)
    else:
        content = await fetch_and_extract(url)

    if not content:
        return f"Sisältöä ei voitu hakea osoitteesta: {url}"

    async with async_session() as session:
        party_obj = None
        if party:
            result = await session.execute(
                select(Party).where(Party.abbreviation == party.upper())
            )
            party_obj = result.scalar_one_or_none()

        source = Source(
            source_type=SourceType.PDF if url.lower().endswith(".pdf") else SourceType.WEBSITE,
            url=url,
            title=content["title"],
            status=SourceStatus.INDEXED,
            party_id=party_obj.id if party_obj else None,
        )
        session.add(source)
        await session.flush()

        doc = Document(
            source_id=source.id,
            title=content["title"],
            content_text=content["text"],
            party_id=party_obj.id if party_obj else None,
            language="fi",
        )
        session.add(doc)
        await session.commit()

    return f"Indeksoitu: {content['title']} ({len(content['text']):,} merkkiä) — {url}"


@mcp.tool()
async def list_documents(party: str | None = None) -> str:
    """Listaa tietokannan dokumentit.

    Args:
        party: Rajaa puolueeseen (esim. "VIHR")
    """
    async with async_session() as session:
        stmt = (
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

        if party:
            stmt = stmt.where(Party.abbreviation == party.upper())

        result = await session.execute(stmt)
        rows = result.all()

    lines = [f"{'Puolue':<8} {'Nimi':<45} {'Docs':>5} {'Merkkejä':>12}"]
    lines.append("-" * 75)
    for abbr, name, count, chars in rows:
        lines.append(f"{abbr:<8} {name[:44]:<45} {count:>5} {chars or 0:>12,}")

    return "\n".join(lines)


if __name__ == "__main__":
    mcp.run()
