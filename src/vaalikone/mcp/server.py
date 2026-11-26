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


from fastmcp import FastMCP
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

# Load config
from vaalikone.core.config import ensure_llm_env, get_settings
from vaalikone.db.engine import create_db_engine

# Models
from vaalikone.models.candidate import Candidate
from vaalikone.models.document import Document
from vaalikone.models.election import Election
from vaalikone.models.embedding import Embedding
from vaalikone.models.party import Party
from vaalikone.models.representative import Representative
from vaalikone.models.source import Source
from vaalikone.models.vote import Vote
from vaalikone.models.voting import Voting

settings = get_settings()
ensure_llm_env()

# Database setup
engine = create_db_engine(settings.DATABASE_URL)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

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
    from vaalikone.core.config import is_read_only
    from vaalikone.ingest.connectors.pdf import fetch_and_extract_pdf
    from vaalikone.ingest.connectors.web import fetch_and_extract
    from vaalikone.models.source import SourceStatus, SourceType

    if is_read_only():
        return "Read-only mode: ingest ei ole käytössä ilman API-avainta."

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


@mcp.tool()
async def search_votes(
    representative: str | None = None,
    subject_contains: str | None = None,
    limit: int = 20,
) -> str:
    """Hae kansanedustajien äänestyksiä (edustajakohtaiset äänet, vaalikausi 2023→).

    Args:
        representative: Kansanedustajan nimi (esim. "Marin")
        subject_contains: Hae äänestyksen asiasta, otsikosta tai asiakirjasta (esim. "Nato",
            "HE 109/2024")
        limit: Montako tulosta (max 100)
    """
    from vaalikone.ingest.votes import subject_title
    from vaalikone.query.hybrid_search import escape_ilike

    async with async_session() as session:
        stmt = (
            select(Representative.first_name, Representative.last_name,
                   Party.abbreviation, Vote, Voting)
            .join(Representative, Vote.representative_id == Representative.id)
            .outerjoin(Party, Representative.party_id == Party.id)
            .outerjoin(Voting, Voting.voting_id == Vote.subject)
        )
        if representative:
            stmt = stmt.where(
                (Representative.first_name + " " + Representative.last_name).ilike(
                    f"%{escape_ilike(representative)}%", escape="\\"
                )
            )
        if subject_contains:
            pattern = f"%{escape_ilike(subject_contains)}%"
            stmt = stmt.where(
                Voting.item_title.ilike(pattern, escape="\\")
                | Voting.title.ilike(pattern, escape="\\")
                | Voting.document_ref.ilike(pattern, escape="\\")
                | Vote.subject_title.ilike(pattern, escape="\\")
            )
        stmt = stmt.order_by(Vote.voted_at.desc().nullslast()).limit(min(limit, 100))
        rows = (await session.execute(stmt)).all()

    if not rows:
        return "Ei äänestyksiä hakuehdoilla."
    lines = [f"{'Kansanedustaja':<25} {'Puolue':<7} {'Pvm':<10} {'Ääni':<7} Asia"]
    lines.append("-" * 100)
    for fn, ln, party, vote, voting in rows:
        name = f"{fn} {ln}"[:24]
        day = vote.voted_at.strftime("%Y-%m-%d") if vote.voted_at else (vote.session or "")
        title = subject_title(voting) if voting else (vote.subject_title or "")
        lines.append(
            f"{name:<25} {(party or '?'):<7} {day:<10} {vote.vote.value:<7} {title[:90]}"
        )
    return "\n".join(lines)


@mcp.tool()
async def party_votes(subject_contains: str, limit: int = 10) -> str:
    """Miten eduskuntaryhmät äänestivät: täysistuntoäänestysten ryhmäjakaumat (2019→).

    Args:
        subject_contains: Hae asian otsikosta, äänestyksen otsikosta tai asiakirjasta
            (esim. "Nato", "työttömyysturva", "HE 109/2024")
        limit: Montako äänestystä (max 50)
    """
    from vaalikone.ingest.votes import subject_title
    from vaalikone.query.hybrid_search import escape_ilike

    pattern = f"%{escape_ilike(subject_contains)}%"
    async with async_session() as session:
        stmt = (
            select(Voting)
            .where(
                Voting.item_title.ilike(pattern, escape="\\")
                | Voting.title.ilike(pattern, escape="\\")
                | Voting.document_ref.ilike(pattern, escape="\\")
            )
            .where(Voting.cancelled.is_(False))
            .order_by(Voting.voted_at.desc().nullslast())
            .limit(min(limit, 50))
        )
        votings = (await session.execute(stmt)).scalars().all()

    if not votings:
        return "Ei äänestyksiä hakuehdoilla."
    out = []
    for v in votings:
        r = v.result or {}
        day = v.voted_at.strftime("%Y-%m-%d") if v.voted_at else ""
        out.append(f"## {day} {subject_title(v)}")
        out.append(
            f"Tulos: jaa {r.get('jaa')}, ei {r.get('ei')}, tyhjä {r.get('tyhja')}, "
            f"poissa {r.get('poissa')} ({v.stage or ''})"
        )
        groups = sorted((v.group_results or {}).items(), key=lambda kv: -sum(
            kv[1].get(k, 0) for k in ("jaa", "ei", "tyhja", "poissa")
        ))
        for code, g in groups:
            label = g.get("party") or code
            out.append(
                f"  {label:<6} jaa {g.get('jaa', 0):>3}  ei {g.get('ei', 0):>3}  "
                f"tyhjä {g.get('tyhja', 0):>2}  poissa {g.get('poissa', 0):>3}"
            )
        out.append("")
    return "\n".join(out)


@mcp.tool()
async def list_candidates(
    year: int = 2023,
    party: str | None = None,
    elected_only: bool = False,
    q: str | None = None,
    limit: int = 30,
) -> str:
    """Listaa vaalien ehdokkaat Tilastokeskus-datasta (äänimäärät, valintatieto, vaalipiiri).

    Args:
        year: Vaalivuosi (esim. 2023)
        party: Rajaa puolueeseen (esim. "SDP")
        elected_only: Vain valitut
        q: Hae ehdokkaan nimellä
        limit: Montako tulosta (max 200)
    """
    async with async_session() as session:
        election = await session.execute(
            select(Election).where(Election.year == year)
        )
        election = election.scalar_one_or_none()
        if not election:
            return (
                f"Ei vaalia vuodelle {year} tietokannassa. "
                f"Aja ensin: vaalikone ingest candidates --year {year}"
            )

        stmt = (
            select(
                Candidate.candidate_number,
                Candidate.first_name,
                Candidate.last_name,
                Party.abbreviation,
                Candidate.constituency,
                Candidate.votes,
                Candidate.elected,
            )
            .outerjoin(Party, Candidate.party_id == Party.id)
            .where(Candidate.election_id == election.id)
        )
        if party:
            stmt = stmt.where(Party.abbreviation == party.upper())
        if elected_only:
            stmt = stmt.where(Candidate.elected.is_(True))
        if q:
            from vaalikone.query.hybrid_search import escape_ilike

            stmt = stmt.where(
                (Candidate.first_name + " " + Candidate.last_name).ilike(
                    f"%{escape_ilike(q)}%", escape="\\"
                )
            )
        stmt = stmt.order_by(Candidate.votes.desc().nullslast()).limit(min(limit, 200))
        result = await session.execute(stmt)
        rows = result.all()

    if not rows:
        return "Ei ehdokkaita hakuehdoilla."
    lines = [f"Ehdokkaat {election.name}" + (f" / {party}" if party else "")]
    lines.append(f"{'Nro':<9} {'Nimi':<28} {'Puolue':<7} {'Vaalipiiri':<28} {'Äänet':>8}  Valittu")
    lines.append("-" * 95)
    for num, fn, ln, party, const, votes, elected in rows:
        name = f"{fn} {ln}"[:27]
        lines.append(
            f"{(num or ''):<9} {name:<28} {(party or '?'):<7} {(const or '')[:27]:<28} "
            f"{(votes or 0):>8,}  {'kyllä' if elected else 'ei'}"
        )
    return "\n".join(lines)


@mcp.tool()
async def compare(q: str, limit_per_party: int = 3) -> str:
    """Vertaa puolueiden kantoja aiheesta ILMAN kielimallia.

    Palauttaa kunkin puolueen lähdeotteet suoraan tietokannasta.

    Args:
        q: Aihe haulle (esim. "metsäpolitiikka", "verotus")
        limit_per_party: Montako otetta per puolue (max 10)
    """
    from vaalikone.query.hybrid_search import text_search

    async with async_session() as session:
        results = await text_search(session, q, limit=min(limit_per_party, 10) * 20)

    by_party: dict[str, list[dict]] = {}
    for r in results:
        by_party.setdefault(r.get("party") or "muu", []).append(r)
    lines = [f"Vertailu aiheesta: {q}", ""]
    for party, items in sorted(
        by_party.items(),
        key=lambda kv: max(x.get("relevance") or 0 for x in kv[1]),
        reverse=True,
    ):
        lines.append(f"== {party} ==")
        top = sorted(items, key=lambda x: x.get("relevance") or 0, reverse=True)
        for item in top[:limit_per_party]:
            import re

            snip = re.sub(r"<[^>]+>", "", item.get("snippet") or "")[:300].replace("\n", " ")
            lines.append(f"- {item.get('title')} (osuvuus {item.get('relevance', 0):.3f})")
            lines.append(f"  {snip}")
        lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    mcp.run()
