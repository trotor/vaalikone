import asyncio
import re

import click
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

from vaalikone.core.config import get_settings
from vaalikone.db.engine import create_db_engine
from vaalikone.ingest.connectors.eduskunta import EduskuntaClient
from vaalikone.ingest.connectors.pdf import extract_pdf_bytes, fetch_and_extract_pdf
from vaalikone.ingest.connectors.tilastokeskus import TilastokeskusClient
from vaalikone.ingest.connectors.web import fetch_and_extract
from vaalikone.ingest.url_validation import UnsafeURLError, validate_public_url
from vaalikone.models.candidate import Candidate
from vaalikone.models.document import ContentType, Document
from vaalikone.models.election import Election, ElectionType
from vaalikone.models.embedding import Embedding
from vaalikone.models.party import Party
from vaalikone.models.representative import Representative
from vaalikone.models.source import Source, SourceStatus, SourceType
from vaalikone.models.vote import Vote, VoteChoice


async def _insert_ignore(
    session: AsyncSession, model, values: dict, conflict: list, index_where=None
) -> bool:
    """Insert unless a conflicting row exists. Returns True if added.

    PostgreSQL: INSERT ... ON CONFLICT DO NOTHING.
    SQLite: SELECT-then-INSERT (no partial-index support for ON CONFLICT).
    """
    bind = session.bind
    if bind is not None and bind.dialect.name == "sqlite":
        q = select(model).where(*[getattr(model, c) == values.get(c) for c in conflict])
        if (await session.execute(q)).scalar_one_or_none() is not None:
            return False
        session.add(model(**values))
        return True
    kwargs = {"index_elements": conflict}
    if index_where is not None:
        kwargs["index_where"] = index_where
    stmt = pg_insert(model).values(**values).on_conflict_do_nothing(**kwargs)
    result = await session.execute(stmt)
    return bool(result.rowcount)

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
    return mapping.get((api_vote or "").strip(), VoteChoice.POISSA)


async def _get_session():
    settings = get_settings()
    engine = create_db_engine(settings.DATABASE_URL)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return engine, async_session


async def _find_party(session: AsyncSession, api_party: str) -> Party | None:
    abbr = PARTY_MAP.get((api_party or "").strip().lower(), (api_party or "").strip().upper())
    result = await session.execute(
        select(Party).where(Party.abbreviation == abbr).limit(1)
    )
    return result.scalars().first()


def _enqueue(task_name: str, **kwargs):
    """Enqueue a Celery task; returns task id. Falls back to error if Redis is down."""
    from vaalikone.workers import tasks

    task = getattr(tasks, task_name)
    result = task.delay(**kwargs)
    click.echo(f"Enqueued task {task_name} (id={result.id})")
    return result.id


async def _delete_source_by_url(session: AsyncSession, url: str) -> int:
    """Poista URL:n lähteet, dokumentit ja embeddingit. Palauttaa poistettujen dok. määrän."""
    src_ids = (await session.execute(select(Source.id).where(Source.url == url))).scalars().all()
    if not src_ids:
        return 0
    doc_ids = (
        await session.execute(select(Document.id).where(Document.source_id.in_(src_ids)))
    ).scalars().all()
    if doc_ids:
        await session.execute(delete(Embedding).where(Embedding.document_id.in_(doc_ids)))
        await session.execute(delete(Document).where(Document.id.in_(doc_ids)))
    await session.execute(delete(Source).where(Source.id.in_(src_ids)))
    await session.flush()
    return len(doc_ids)


async def _store_document(
    session: AsyncSession,
    *,
    source_type: SourceType,
    url: str | None,
    title: str,
    text: str,
    content_type: ContentType,
    party_id=None,
    representative_id=None,
    published_at=None,
    metadata: dict | None = None,
    language: str = "fi",
    replace: bool = False,
) -> bool:
    """Store a source+document, skipping if the URL was already indexed.

    replace=True poistaa saman URL:n aiemman lähteen, dokumentit ja embeddingit
    ennen tallennusta (käytä kun aiempi haku tuotti rikkinäisen/ohuen tekstin).
    Returns True if stored, False if skipped."""
    if url and replace:
        await _delete_source_by_url(session, url)
    if url:
        existing = await session.execute(select(Source).where(Source.url == url).limit(1))
        source = existing.scalars().first()
        if source:
            # Upgrade content_type if the document was stored before types existed
            if content_type != ContentType.MUU:
                doc_res = await session.execute(
                    select(Document).where(Document.source_id == source.id).limit(1)
                )
                doc = doc_res.scalars().first()
                if doc and doc.content_type == ContentType.MUU:
                    doc.content_type = content_type
                    doc.metadata_ = {**(doc.metadata_ or {}), **(metadata or {})}
            return False

    source = Source(
        source_type=source_type,
        url=url,
        title=title,
        status=SourceStatus.INDEXED,
        party_id=party_id,
        representative_id=representative_id,
        metadata_=metadata,
    )
    session.add(source)
    await session.flush()

    doc = Document(
        source_id=source.id,
        title=title,
        content_text=text,
        content_type=content_type,
        party_id=party_id,
        representative_id=representative_id,
        published_at=published_at,
        language=language or "fi",
        metadata_=metadata,
    )
    session.add(doc)
    return True


async def _ingest_representatives() -> dict:
    client = EduskuntaClient()
    click.echo("Fetching representatives from eduskunta API...")
    reps = await client.fetch_representatives()
    click.echo(f"Fetched {len(reps)} representatives from API.")

    engine, async_session = await _get_session()

    async with async_session() as session:
        source = Source(
            source_type=SourceType.API,
            url=f"{client.base_url}/api/v1/tables/MemberOfParliament/rows",
            title="Eduskunta - Kansanedustajat",
            status=SourceStatus.INDEXED,
        )
        session.add(source)

        added = 0
        skipped = 0
        for rep_data in reps:
            person_id = str(rep_data.get("personId", "") or "")
            first_name = rep_data.get("firstname", "")
            last_name = rep_data.get("lastname", "")

            if not first_name or not last_name:
                skipped += 1
                continue

            party = await _find_party(session, rep_data.get("party", ""))

            if person_id:
                if await _insert_ignore(
                    session, Representative,
                    {
                        "person_id": person_id,
                        "first_name": first_name,
                        "last_name": last_name,
                        "party_id": party.id if party else None,
                        "social_media": {"eduskunta_person_id": person_id},
                    },
                    ["person_id"],
                ):
                    added += 1
                else:
                    skipped += 1
            else:
                result = await session.execute(
                    select(Representative).where(
                        Representative.first_name == first_name,
                        Representative.last_name == last_name,
                    )
                )
                if result.scalar_one_or_none():
                    skipped += 1
                    continue
                session.add(
                    Representative(
                        first_name=first_name,
                        last_name=last_name,
                        party_id=party.id if party else None,
                        social_media={"eduskunta_person_id": person_id} if person_id else None,
                    )
                )
                added += 1

        await session.commit()
        click.echo(f"Added {added} representatives, skipped {skipped}.")

    await engine.dispose()
    return {"added": added, "skipped": skipped}


async def _fetch_vote_subject_map(
    client: EduskuntaClient, max_pages: int | None = None
) -> dict[str, str]:
    """Map AanestysId -> AanestysOtsikko (vote subject title)."""
    summaries = await client.fetch_vote_summaries(max_pages=max_pages)
    return {
        str(s.get("AanestysId", "")): (s.get("AanestysOtsikko") or "").strip()
        for s in summaries
        if s.get("AanestysId")
    }


async def _ingest_votes(max_pages: int | None = None) -> dict:
    client = EduskuntaClient()
    click.echo("Fetching votes from eduskunta API...")
    votes = await client.fetch_votes(max_pages=max_pages)
    click.echo(f"Fetched {len(votes)} vote records from API.")
    click.echo("Fetching vote subjects...")
    subjects = await _fetch_vote_subject_map(client, max_pages=max_pages)

    engine, async_session = await _get_session()

    async with async_session() as session:
        source = Source(
            source_type=SourceType.API,
            url=f"{client.base_url}/api/v1/tables/SaliDBAanestysEdustaja/rows",
            title="Eduskunta - Äänestykset",
            status=SourceStatus.INDEXED,
        )
        session.add(source)

        added = 0
        skipped = 0
        with session.no_autoflush:
            # Cache henkilonumero/name -> representative to avoid a query per vote row
            rep_cache: dict[str, Representative | None] = {}
            for vote_data in votes:
                person_id = str(vote_data.get("EdustajaHenkiloNumero", "") or "")
                first_name = vote_data.get("EdustajaEtunimi", "")
                last_name = vote_data.get("EdustajaSukunimi", "")
                key = person_id or f"{first_name}|{last_name}"
                if key not in rep_cache:
                    if person_id:
                        result = await session.execute(
                            select(Representative)
                            .where(Representative.person_id == person_id)
                            .limit(1)
                        )
                    else:
                        result = await session.execute(
                            select(Representative)
                            .where(
                                Representative.first_name == first_name,
                                Representative.last_name == last_name,
                            )
                            .limit(1)
                        )
                    rep_cache[key] = result.scalar_one_or_none()
                rep = rep_cache[key]
                if not rep:
                    skipped += 1
                    continue

                aanestys_id = str(vote_data.get("AanestysId", "") or "")
                if not aanestys_id:
                    skipped += 1
                    continue

                if await _insert_ignore(
                    session, Vote,
                    {
                        "representative_id": rep.id,
                        "session": str(vote_data.get("IstuntoVPVuosi", "") or "") or None,
                        "subject": aanestys_id,
                        "subject_title": subjects.get(aanestys_id),
                        "vote": _map_vote(vote_data.get("EdustajaAanestys", "Poissa")),
                    },
                    ["representative_id", "subject"],
                    index_where=Vote.subject.isnot(None),
                ):
                    added += 1
                else:
                    skipped += 1

        await session.commit()
        click.echo(f"Added {added} votes, skipped {skipped}.")

    await engine.dispose()
    return {"added": added, "skipped": skipped}


async def _ingest_vote_subjects(max_pages: int | None = None) -> dict:
    """Backfill votes.subject_title from SaliDBAanestys for existing votes."""
    client = EduskuntaClient()
    click.echo("Fetching vote subjects...")
    subjects = await _fetch_vote_subject_map(client, max_pages=max_pages)
    click.echo(f"Got {len(subjects)} vote subjects.")

    engine, async_session = await _get_session()
    async with async_session() as session:
        from sqlalchemy import update

        updated = 0
        for aanestys_id, title in subjects.items():
            if not title:
                continue
            result = await session.execute(
                update(Vote)
                .where(Vote.subject == aanestys_id, Vote.subject_title.is_(None))
                .values(subject_title=title)
            )
            updated += result.rowcount or 0
        await session.commit()
        click.echo(f"Updated subject_title on {updated} votes.")
    await engine.dispose()
    return {"updated": updated}


def _strip_html(html: str) -> str:
    text = re.sub(r"(?is)<(script|style).*?</\1>", " ", html)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"&auml;", "ä", text)
    text = re.sub(r"&ouml;", "ö", text)
    text = re.sub(r"&auml;", "ä", text)
    text = re.sub(r"&#228;", "ä", text)
    text = re.sub(r"&#246;", "ö", text)
    text = re.sub(r"&amp;", "&", text)
    return re.sub(r"\s+", " ", text).strip()


async def _ingest_speeches(query: str, max_results: int = 100, start_from: int = 0) -> dict:
    """Ingest täysistuntopuheenvuorot (floor speeches) via the new eduskunta search API."""
    client = EduskuntaClient()
    click.echo(f"Searching speeches for {query!r}...")
    data = await client.search_speeches(query, max_results=max_results, start_from=start_from)
    results = data.get("results", [])
    total = data.get("searchMetadata", {}).get("totalResultCount", len(results))
    click.echo(f"Found {total} speeches, processing {len(results)}.")

    engine, async_session = await _get_session()
    async with async_session() as session:
        stored = 0
        skipped = 0
        for r in results:
            puh = r.get("puheenvuoro") or {}
            text = (puh.get("puheenvuoro") or "").strip()
            if not text:
                skipped += 1
                continue
            puhuja = puh.get("puhuja") or {}
            person_id = str(puhuja.get("henkilonro", "") or "") or None
            rep = None
            party = None
            if person_id:
                res = await session.execute(
                    select(Representative).where(Representative.person_id == person_id).limit(1)
                )
                rep = res.scalar_one_or_none()
            if rep and rep.party_id:
                party = rep.party
            if not party:
                party = await _find_party(session, (puhuja.get("lisatieto") or "").strip())

            speech_id = puh.get("id") or r.get("id")
            tunnus_fi = (puh.get("tunnus") or {}).get("fi", "")
            url = f"https://www.eduskunta.fi/taysistunto/poytakirja/{tunnus_fi}"
            title = (
                f"Puheenvuoro {(puh.get('valtiopaiva') or '')} "
                f"{(puhuja.get('etunimi', '') + ' ' + puhuja.get('sukunimi', '')).strip()}"
            ).strip()
            from datetime import datetime

            published = None
            try:
                published = datetime.fromisoformat(puh.get("aloitushetki"))
            except Exception:
                pass

            ok = await _store_document(
                session,
                source_type=SourceType.API,
                url=f"{client.search_url}/puheenvuoro/{speech_id}" if speech_id else url,
                title=title,
                text=text,
                content_type=ContentType.PUHEENVUORO,
                party_id=party.id if party else (rep.party_id if rep else None),
                representative_id=rep.id if rep else None,
                published_at=published,
                metadata={
                    "speech_id": speech_id,
                    "valtiopaiva": puh.get("valtiopaiva"),
                    "taysistunto": puh.get("taysistuntonumero"),
                    "asia": (puh.get("asia") or {}).get("fi", {}).get("nimeketeksti"),
                },
            )
            if ok:
                stored += 1
            else:
                skipped += 1
        await session.commit()
        click.echo(f"Stored {stored} speeches, skipped {skipped}.")
    await engine.dispose()
    return {"stored": stored, "skipped": skipped, "total": total}


async def _ingest_questions(
    max_results: int = 100, start_from: int = 0, valtiopaiva: str | None = None
) -> dict:
    """Ingest kirjalliset kysymykset (KK) via the new eduskunta search API."""
    client = EduskuntaClient()
    click.echo("Listing written questions (KK)...")
    data = await client.search_written_questions(
        max_results=max_results, start_from=start_from, valtiopaiva=valtiopaiva
    )
    results = data.get("results", [])
    total = data.get("searchMetadata", {}).get("totalResultCount", len(results))
    click.echo(f"Found {total} written questions, processing {len(results)}.")

    engine, async_session = await _get_session()
    async with async_session() as session:
        stored = 0
        skipped = 0
        for r in results:
            vpa = r.get("valtiopaivaasia") or {}
            tunnus = vpa.get("eduskuntatunnus") or r.get("id")
            if isinstance(tunnus, dict):
                tunnus = tunnus.get("fi") or tunnus.get("sv")
            if not tunnus:
                skipped += 1
                continue
            title = (vpa.get("nimeke") or {}).get("fi") or tunnus
            xml = await client.fetch_document_xml(tunnus)
            text = _strip_html(xml) if xml else ""
            if not text:
                skipped += 1
                continue
            first_signer = vpa.get("ensimmainenAllekirjoittaja") or {}
            signer_name = " ".join(
                p for p in [first_signer.get("etunimi"), first_signer.get("sukunimi")] if p
            )
            rep = None
            if signer_name:
                parts = signer_name.split(" ", 1)
                res = await session.execute(
                    select(Representative).where(
                        Representative.first_name == (parts[1] if len(parts) > 1 else parts[0]),
                        Representative.last_name == (parts[0] if len(parts) > 1 else ""),
                    ).limit(1)
                )
                rep = res.scalar_one_or_none()
            from datetime import datetime

            published = None
            try:
                published = datetime.fromisoformat((vpa.get("laadintapvm") or {}).get("fi") or "")
            except Exception:
                pass
            ok = await _store_document(
                session,
                source_type=SourceType.API,
                url=f"https://www.eduskunta.fi/valtiopaivaasiat/{tunnus.replace(' ', '%20')}",
                title=f"{tunnus}: {title}"[:500],
                text=text,
                content_type=ContentType.KIRJALLINEN_KYSYMYS,
                party_id=rep.party_id if rep else None,
                representative_id=rep.id if rep else None,
                published_at=published,
                metadata={"eduskuntatunnus": tunnus, "signer": signer_name},
            )
            if ok:
                stored += 1
            else:
                skipped += 1
        await session.commit()
        click.echo(f"Stored {stored} written questions, skipped {skipped}.")
    await engine.dispose()
    return {"stored": stored, "skipped": skipped, "total": total}


async def _ingest_candidates(year: int = 2023, election: str = "eduskuntavaalit") -> dict:
    """Ingest election candidates (ehdokkaat) from Tilastokeskus PxWeb."""
    from vaalikone.ingest.connectors.tilastokeskus import (
        EDUSKUNTAVAALIT_EHDOKKAAT_TABLE,
        EUROVAALIT_EHDOKKAAT_TABLE,
        KUNTAVAALIT_VAALIPIIRI_TABLES,
        PRESIDENTINVAALI_EHDOKKAAT_TABLE,
    )

    client = TilastokeskusClient()
    etype = ElectionType(election)

    if etype == ElectionType.EUROPARLAMENTTIVAALIT:
        click.echo(f"Fetching europarlamenttivaalit {year} candidates from Tilastokeskus...")
        candidates = await client.fetch_election_results(
            EUROVAALIT_EHDOKKAAT_TABLE, str(year), constituency="Koko Suomi"
        )
        source_url = f"https://pxdata.stat.fi/PxWeb/api/v1/fi/StatFin/{EUROVAALIT_EHDOKKAAT_TABLE}"
    elif etype == ElectionType.PRESIDENTINVAALI:
        click.echo(f"Fetching presidentinvaali {year} candidates (koko maa, kierrokset 1-2)...")
        candidates = await client.fetch_election_results(
            PRESIDENTINVAALI_EHDOKKAAT_TABLE, str(year), area="SSS",
            kierros=["1", "2"], constituency="Koko Suomi",
        )
        source_url = (
            f"https://pxdata.stat.fi/PxWeb/api/v1/fi/StatFin/{PRESIDENTINVAALI_EHDOKKAAT_TABLE}"
        )
    elif etype == ElectionType.KUNTAVAALIT:
        click.echo(f"Fetching kuntavaalit {year} candidates per vaalipiiri...")
        all_candidates = []
        for vaalipiiri, table in KUNTAVAALIT_VAALIPIIRI_TABLES.items():
            try:
                cs = await client.fetch_municipal_candidates(
                    table, vaalipiiri, year=str(year)
                )
                click.echo(f"  {vaalipiiri}: {len(cs)} ehdokasta")
                all_candidates.extend(cs)
            except Exception as e:
                click.echo(f"  [fail] {vaalipiiri} ({table}): {type(e).__name__}: {e}")
        candidates = all_candidates
        source_url = "https://pxdata.stat.fi/PxWeb/api/v1/fi/StatFin/kvaa/"
    else:
        click.echo(f"Fetching {election} {year} candidates from Tilastokeskus...")
        candidates = await client.fetch_candidates()
        source_url = f"https://pxdata.stat.fi/PxWeb/api/v1/fi/StatFin/{EDUSKUNTAVAALIT_EHDOKKAAT_TABLE}"
    click.echo(f"Fetched {len(candidates)} candidates total.")

    engine, async_session = await _get_session()
    async with async_session() as session:
        election_row = await session.execute(
            select(Election).where(
                Election.year == year, Election.election_type == etype
            )
        )
        election_row = election_row.scalar_one_or_none()
        if not election_row:
            election_row = Election(
                year=year,
                election_type=etype,
                name={
                    ElectionType.KUNTAVAALIT: f"Kuntavaalit {year}",
                    ElectionType.EUROPARLAMENTTIVAALIT: f"Europarlamenttivaalit {year}",
                    ElectionType.PRESIDENTINVAALI: f"Presidentinvaali {year}",
                }.get(etype, f"Eduskuntavaalit {year}"),
                source_url=source_url,
            )
            session.add(election_row)
            await session.flush()
        election = election_row

        added = 0
        skipped = 0
        for c in candidates:
            party = await _find_party(session, c.get("party_abbr") or "")
            if await _insert_ignore(
                session, Candidate,
                {
                    "election_id": election.id,
                    "party_id": party.id if party else None,
                    "candidate_number": c["candidate_number"],
                    "first_name": c["first_name"],
                    "last_name": c["last_name"],
                    "constituency": c.get("constituency"),
                    "votes": c.get("votes"),
                    "vote_share": c.get("vote_share"),
                    "comparison_number": c.get("comparison_number"),
                    "elected": bool(c.get("elected")),
                },
                ["election_id", "candidate_number"],
                index_where=Candidate.candidate_number.isnot(None),
            ):
                added += 1
            else:
                skipped += 1
        await session.commit()
        click.echo(f"Added {added} candidates, skipped {skipped}.")
    await engine.dispose()
    return {"added": added, "skipped": skipped}


async def _ingest_pdf(url: str, party_abbr: str | None = None, title_override: str | None = None):
    validate_public_url(url)
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

        await _store_document(
            session,
            source_type=SourceType.PDF,
            url=url,
            title=title,
            text=content["text"],
            content_type=ContentType.MUU,
            party_id=party.id if party else None,
            metadata={"pages": content.get("pages")},
        )
        await session.commit()
        click.echo(f"Stored PDF document: {title}")

    await engine.dispose()


async def _ingest_url(url: str, party_abbr: str | None = None):
    if url.lower().endswith(".pdf"):
        await _ingest_pdf(url, party_abbr)
        return

    validate_public_url(url)
    click.echo(f"Fetching {url}...")
    content = await fetch_and_extract(url)
    if not content:
        click.echo("Failed to extract content from URL.")
        return

    click.echo(f"Extracted: {content['title']} ({len(content['text'])} chars)")

    engine, async_session = await _get_session()
    async with async_session() as session:
        party = None
        if party_abbr:
            party = await _find_party(session, party_abbr)

        await _store_document(
            session,
            source_type=SourceType.WEBSITE,
            url=url,
            title=content["title"],
            text=content["text"],
            content_type=ContentType.MUU,
            party_id=party.id if party else None,
        )
        await session.commit()
        click.echo(f"Stored document: {content['title']}")

    await engine.dispose()


async def _ingest_crawl(
    seed_url: str, party_abbr: str | None = None, depth: int = 2,
    max_pages: int = 50, use_llm: bool = False,
):
    from vaalikone.ingest.connectors.crawler import crawl_site

    validate_public_url(seed_url)

    async def on_found(url, title, chars):
        click.echo(f"  Found: {title} ({chars:,} chars)")

    llm_txt = "on" if use_llm else "off"
    click.echo(f"Crawling {seed_url} (depth={depth}, max={max_pages}, llm={llm_txt})...")
    pages = await crawl_site(
        seed_url,
        max_depth=depth,
        max_pages=max_pages,
        use_llm_filter=use_llm,
        callback=on_found,
    )

    if not pages:
        click.echo("No relevant pages found.")
        return

    engine, async_session = await _get_session()
    async with async_session() as session:
        party = None
        if party_abbr:
            party = await _find_party(session, party_abbr)

        stored = 0
        skipped = 0
        for page in pages:
            ok = await _store_document(
                session,
                source_type=SourceType.WEBSITE,
                url=page["url"],
                title=page["title"],
                text=page["text"],
                content_type=ContentType.MUU,
                party_id=party.id if party else None,
            )
            if ok:
                stored += 1
            else:
                click.echo(f"  Skip (exists): {page['url']}")
                skipped += 1
        await session.commit()
        click.echo(
            f"\nCrawled {len(pages)} pages, stored {stored} new, skipped {skipped}."
        )

    await engine.dispose()


async def _ingest_embed(model: str | None = None, force: bool = False) -> dict:
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
    return {"documents": n_docs, "chunks": n_chunks}


KIND_TO_CONTENT_TYPE = {
    "vaaliohjelma": ContentType.VAALIOHJELMA,
    "puolueohjelma": ContentType.PUOLUEOHJELMA,
    "varjobudjetti": ContentType.VARJOBUDJETTI,
    "hallitusohjelma": ContentType.HALLITUSOHJELMA,
    "kuntavaaliohjelma": ContentType.KUNTAVAALIOHJELMA,
    "eurovaaliohjelma": ContentType.EUROVAALIOHJELMA,
}

# Alle tämän mittainen ohjelmateksti on lähes aina laskeutumis- tai navigaatiosivu.
# Ylikirjoitettavissa sources.yaml-rivillä (min_chars).
DEFAULT_MIN_PROGRAM_CHARS = 2000
# Crawlatusta sivusta tulee ohjelmadokumentti (kind) vain jos tekstiä on vähintään tämän verran;
# lyhyemmät (yhteystiedot, uutislistat, ehdokasgalleriat) tallennetaan tyypillä MUU.
CRAWL_MIN_PROGRAM_CHARS = 3000


def _load_sources_yaml(path: str = "config/sources.yaml") -> list[dict]:
    import yaml

    with open(path) as f:
        data = yaml.safe_load(f)
    return data.get("sources", []) if data else []


async def _ingest_programs(
    party_filter: str | None = None,
    kind_filter: str | None = None,
    refresh: bool = False,
) -> dict:
    """Ingest all party programs/shadow budgets listed in config/sources.yaml.

    refresh=True korvaa aiemmin tallennetun saman URL:n dokumentin (esim. jos
    aiempi haku tuotti vain laskeutumissivun)."""
    entries = _load_sources_yaml()
    if party_filter:
        entries = [e for e in entries if e.get("party", "").upper() == party_filter.upper()]
    if kind_filter:
        entries = [e for e in entries if e.get("kind") == kind_filter]

    click.echo(f"Ingesting {len(entries)} entries from config/sources.yaml...")
    stats = {"stored": 0, "skipped": 0, "failed": 0}

    for entry in entries:
        party_abbr = entry.get("party", "")
        kind = entry.get("kind", "muu")
        url = entry.get("url", "")
        title = entry.get("title") or url
        stype = entry.get("type", "web")
        content_type = KIND_TO_CONTENT_TYPE.get(kind, ContentType.MUU)
        language = entry.get("language", "fi")
        min_chars = entry.get("min_chars", DEFAULT_MIN_PROGRAM_CHARS)
        meta = {"kind": kind, "program_source": "config/sources.yaml"}
        if entry.get("year"):
            meta["year"] = entry["year"]

        try:
            validate_public_url(url)
            engine, async_session = await _get_session()
            async with async_session() as session:
                party = await _find_party(session, party_abbr) if party_abbr else None
                if party_abbr and not party:
                    click.echo(f"  [skip] unknown party {party_abbr}: {title}")
                    stats["skipped"] += 1
                    await engine.dispose()
                    continue

                if stype == "pdf" or url.lower().endswith(".pdf"):
                    content = None
                    for attempt in range(3):
                        try:
                            content = await fetch_and_extract_pdf(url)
                            break
                        except Exception as e:
                            if "429" in str(e) and attempt < 2:
                                await asyncio.sleep(5 * (attempt + 1))
                                continue
                            raise
                    if not content:
                        raise ValueError("PDF text extraction failed")
                    text, pages = content["text"], content.get("pages")
                    meta["pages"] = pages
                    src_type = SourceType.PDF
                elif stype == "crawl":
                    from vaalikone.ingest.connectors.crawler import crawl_site

                    pages_list = await crawl_site(
                        url,
                        max_depth=entry.get("depth", 1),
                        max_pages=entry.get("max_pages", 20),
                    )
                    stored = 0
                    for page in pages_list:
                        is_program = len(page["text"]) >= CRAWL_MIN_PROGRAM_CHARS
                        ok = await _store_document(
                            session,
                            source_type=SourceType.WEBSITE,
                            url=page["url"],
                            title=page["title"],
                            text=page["text"],
                            content_type=content_type if is_program else ContentType.MUU,
                            party_id=party.id if party else None,
                            metadata={**meta, "seed_url": url},
                            language=language,
                            replace=refresh,
                        )
                        if ok:
                            stored += 1
                    await session.commit()
                    await engine.dispose()
                    click.echo(f"  [crawl] {party_abbr} {title}: {stored} sivua")
                    stats["stored"] += stored
                    continue
                else:
                    content = None
                    for attempt in range(3):
                        try:
                            content = await fetch_and_extract(url)
                            break
                        except Exception as e:
                            if "429" in str(e) and attempt < 2:
                                await asyncio.sleep(5 * (attempt + 1))
                                continue
                            raise
                    if not content:
                        raise ValueError("web text extraction failed")
                    text = content["text"]
                    src_type = SourceType.WEBSITE

                if len(text.strip()) < min_chars:
                    raise ValueError(
                        f"vain {len(text.strip())} merkkiä (< {min_chars}) — "
                        "todennäköisesti laskeutumissivu, tarkista URL"
                    )

                ok = await _store_document(
                    session,
                    source_type=src_type,
                    url=url,
                    title=title,
                    text=text,
                    content_type=content_type,
                    party_id=party.id if party else None,
                    metadata=meta,
                    language=language,
                    replace=refresh,
                )
                await session.commit()
                if ok:
                    click.echo(f"  [ok] {party_abbr} {kind}: {title} ({len(text):,} chars)")
                    stats["stored"] += 1
                else:
                    click.echo(f"  [skip exists] {party_abbr}: {title}")
                    stats["skipped"] += 1
            await engine.dispose()
        except Exception as e:
            click.echo(f"  [fail] {party_abbr} {title}: {type(e).__name__}: {str(e)[:100]}")
            stats["failed"] += 1

    click.echo(
        f"\nDone: {stats['stored']} stored, {stats['skipped']} skipped, "
        f"{stats['failed']} failed."
    )
    return stats


@click.group()
def ingest():
    """Ingest data from various sources."""
    pass


@ingest.command(name="programs")
@click.option("--party", default=None, help="Only one party (e.g. SDP)")
@click.option("--kind", default=None, type=click.Choice(sorted(KIND_TO_CONTENT_TYPE)))
@click.option(
    "--refresh", is_flag=True,
    help="Korvaa jo tallennetut saman URL:n dokumentit (esim. ohuet laskeutumissivut)",
)
@click.option("--queue", "queue", is_flag=True, help="Run as background Celery task")
def programs(party: str | None, kind: str | None, refresh: bool, queue: bool):
    """Ingest all party programs and shadow budgets from config/sources.yaml."""
    if queue:
        _enqueue("ingest_programs_task", party_filter=party, kind_filter=kind, refresh=refresh)
        return
    asyncio.run(_ingest_programs(party, kind, refresh=refresh))


@ingest.command()
@click.option("--queue", "queue", is_flag=True, help="Run as background Celery task")
def representatives(queue: bool):
    """Fetch and store representatives from eduskunta API."""
    if queue:
        _enqueue("ingest_representatives_task")
        return
    asyncio.run(_ingest_representatives())


@ingest.command()
@click.option("--max-pages", default=None, type=int, help="Limit number of API pages to fetch.")
@click.option("--queue", "queue", is_flag=True, help="Run as background Celery task")
def votes(max_pages: int | None, queue: bool):
    """Fetch and store votes from eduskunta API (with subject titles)."""
    if queue:
        _enqueue("ingest_votes_task", max_pages=max_pages)
        return
    asyncio.run(_ingest_votes(max_pages))


@ingest.command(name="vote-subjects")
@click.option("--max-pages", default=None, type=int, help="Limit number of API pages to fetch.")
@click.option("--queue", "queue", is_flag=True, help="Run as background Celery task")
def vote_subjects(max_pages: int | None, queue: bool):
    """Backfill vote subject titles (äänestysten otsikot) for existing votes."""
    if queue:
        _enqueue("ingest_vote_subjects_task", max_pages=max_pages)
        return
    asyncio.run(_ingest_vote_subjects(max_pages))


@ingest.command()
@click.argument("query")
@click.option("--max-results", default=100, type=int, help="How many speeches to fetch.")
@click.option("--start-from", default=0, type=int, help="Offset into search results.")
@click.option("--queue", "queue", is_flag=True, help="Run as background Celery task")
def speeches(query: str, max_results: int, start_from: int, queue: bool):
    """Ingest täysistuntopuheenvuorot (floor speeches) matching a text query."""
    if queue:
        _enqueue(
            "ingest_speeches_task",
            query=query, max_results=max_results, start_from=start_from,
        )
        return
    asyncio.run(_ingest_speeches(query, max_results, start_from))


@ingest.command()
@click.option("--max-results", default=100, type=int, help="How many questions to fetch.")
@click.option("--start-from", default=0, type=int, help="Offset into search results.")
@click.option(
    "--valtiopaiva", default=None, help="Filter by session (e.g. '2023 vp')."
)
@click.option("--queue", "queue", is_flag=True, help="Run as background Celery task")
def questions(max_results: int, start_from: int, valtiopaiva: str | None, queue: bool):
    """Ingest kirjalliset kysymykset (written questions, KK)."""
    if queue:
        _enqueue(
            "ingest_questions_task",
            max_results=max_results, start_from=start_from, valtiopaiva=valtiopaiva,
        )
        return
    asyncio.run(_ingest_questions(max_results, start_from, valtiopaiva))


async def _ingest_campaign_finance(year: int = 2023, election: str = "eduskuntavaalit") -> dict:
    """Ingest vaalirahoitusrivit (vaalirahoitusvalvonta.fi CSV) vaaleille."""
    from sqlalchemy import func as sa_func

    from vaalikone.ingest.connectors.vaalirahoitus import (
        EDUSKUNTAVAALIT_2023_FILES,
        fetch_finance_rows,
    )
    from vaalikone.models.campaign_finance import CampaignFinance

    etype = ElectionType(election)
    files = (
        {"eduskuntavaalit": {"2023": EDUSKUNTAVAALIT_2023_FILES}}
        .get(election, {}).get(str(year))
    )
    if not files:
        click.echo(f"No campaign finance files configured for {election} {year}.")
        return {"added": 0, "skipped": 0}

    engine, async_session = await _get_session()
    async with async_session() as session:
        election_row = await session.execute(
            select(Election).where(Election.year == year, Election.election_type == etype)
        )
        election_row = election_row.scalar_one_or_none()

        stats = {"added": 0, "skipped": 0}
        for label, url in files.items():
            existing = await session.execute(
                select(sa_func.count(CampaignFinance.id)).where(
                    CampaignFinance.source_url == url
                )
            )
            if existing.scalar():
                click.echo(f"  [skip exists] {label}: {url[:80]}")
                stats["skipped"] += 1
                continue
            click.echo(f"  fetching {label}: {url[:80]}")
            rows = await fetch_finance_rows(url)
            for r in rows:
                party = await _find_party(session, r.get("party_abbr") or "")
                session.add(CampaignFinance(
                    election_id=election_row.id if election_row else None,
                    party_id=party.id if party else None,
                    recipient_first_name=r.get("recipient_first_name"),
                    recipient_last_name=r.get("recipient_last_name"),
                    constituency=r.get("constituency"),
                    donor_name=r.get("donor_name"),
                    donor_business_id=r.get("donor_business_id"),
                    donor_first_names=r.get("donor_first_names"),
                    donor_last_name=r.get("donor_last_name"),
                    donor_municipality=r.get("donor_municipality"),
                    form_numbers=r.get("form_numbers"),
                    loan_name=r.get("loan_name"),
                    loan_term=r.get("loan_term"),
                    amount=r.get("amount"),
                    source_url=url,
                ))
                stats["added"] += 1
            click.echo(f"  [ok] {label}: {len(rows)} rahoitusriviä")
        await session.commit()
    await engine.dispose()
    return stats


@ingest.command(name="campaign-finance")
@click.option("--year", default=2023, type=int, help="Election year (default 2023).")
@click.option(
    "--election", default="eduskuntavaalit",
    type=click.Choice(["eduskuntavaalit", "kuntavaalit", "europarlamenttivaalit",
                       "presidentinvaali"]),
)
def campaign_finance(year: int, election: str):
    """Ingest campaign finance rows (vaalirahoitus) from vaalirahoitusvalvonta.fi."""
    stats = asyncio.run(_ingest_campaign_finance(year, election))
    click.echo(f"Done: {stats['added']} added, {stats['skipped']} skipped.")


@ingest.command()
@click.option("--year", default=2023, type=int,
              help="Election year (default 2023; kuntavaalit 2025).")
@click.option(
    "--election",
    type=click.Choice([
        "eduskuntavaalit", "kuntavaalit", "europarlamenttivaalit", "presidentinvaali",
    ]),
    default="eduskuntavaalit",
    help="Election type (default eduskuntavaalit).",
)
@click.option("--queue", "queue", is_flag=True, help="Run as background Celery task")
def candidates(year: int, election: str, queue: bool):
    """Ingest election candidates (ehdokkaat) from Tilastokeskus."""
    if queue:
        _enqueue("ingest_candidates_task", year=year, election=election)
        return
    asyncio.run(_ingest_candidates(year, election))


@ingest.command()
@click.argument("url")
@click.option("--party", default=None, help="Party abbreviation (e.g. SDP)")
@click.option("--queue", "queue", is_flag=True, help="Run as background Celery task")
def url(url: str, party: str | None, queue: bool):
    """Ingest content from a URL."""
    if queue:
        _enqueue("ingest_url_task", url=url, party=party)
        return
    try:
        asyncio.run(_ingest_url(url, party))
    except UnsafeURLError as e:
        raise click.ClickException(f"URL rejected (SSRF protection): {e}")


@ingest.command()
@click.argument("url")
@click.option("--party", default=None, help="Party abbreviation (e.g. SDP)")
@click.option("--title", default=None, help="Override document title")
@click.option("--queue", "queue", is_flag=True, help="Run as background Celery task")
def pdf(url: str, party: str | None, title: str | None, queue: bool):
    """Ingest a PDF document from URL."""
    if queue:
        _enqueue("ingest_pdf_task", url=url, party=party, title=title)
        return
    try:
        asyncio.run(_ingest_pdf(url, party, title))
    except UnsafeURLError as e:
        raise click.ClickException(f"URL rejected (SSRF protection): {e}")


@ingest.command(name="pdf-file")
@click.argument("file_path", type=click.Path(exists=True))
@click.option("--party", default=None, help="Party abbreviation")
@click.option("--title", default=None, help="Override document title")
def pdf_file(file_path: str, party: str | None, title: str | None):
    """Ingest a local PDF file."""

    async def _run():
        with open(file_path, "rb") as f:
            pdf_bytes = f.read()

        content = extract_pdf_bytes(pdf_bytes, file_path)
        if not content:
            click.echo("Failed to extract text from PDF.")
            return

        doc_title = title or content["title"]
        click.echo(
            f"Extracted: {doc_title} "
            f"({len(content['text'])} chars, {content['pages']} pages)"
        )

        engine, async_session = await _get_session()
        async with async_session() as session:
            party_obj = None
            if party:
                party_obj = await _find_party(session, party)

            await _store_document(
                session,
                source_type=SourceType.PDF,
                url=file_path,
                title=doc_title,
                text=content["text"],
                content_type=ContentType.MUU,
                party_id=party_obj.id if party_obj else None,
                metadata={"pages": content.get("pages")},
            )
            await session.commit()
            click.echo(f"Stored PDF document: {doc_title}")

        await engine.dispose()

    asyncio.run(_run())


@ingest.command()
@click.argument("seed_url")
@click.option("--party", default=None, help="Party abbreviation (e.g. SDP)")
@click.option("--depth", default=2, help="Max link depth to follow (default 2)")
@click.option("--max-pages", default=50, help="Max pages to crawl (default 50)")
@click.option("--use-llm", is_flag=True, help="Use local LLM for relevance filtering")
@click.option("--queue", "queue", is_flag=True, help="Run as background Celery task")
def crawl(seed_url: str, party: str | None, depth: int, max_pages: int, use_llm: bool, queue: bool):
    """Crawl a website recursively, indexing political content."""
    if queue:
        _enqueue(
            "ingest_crawl_task", seed_url=seed_url, party=party,
            depth=depth, max_pages=max_pages, use_llm=use_llm,
        )
        return
    try:
        asyncio.run(_ingest_crawl(seed_url, party, depth, max_pages, use_llm))
    except UnsafeURLError as e:
        raise click.ClickException(f"URL rejected (SSRF protection): {e}")


@ingest.command()
@click.option("--model", default=None, help="Embedding model (default from config)")
@click.option("--force", is_flag=True, help="Re-embed all documents")
@click.option("--queue", "queue", is_flag=True, help="Run as background Celery task")
def embed(model: str | None, force: bool, queue: bool):
    """Generate embeddings for all documents."""
    if queue:
        _enqueue("ingest_embed_task", model=model, force=force)
        return
    asyncio.run(_ingest_embed(model, force))


@ingest.command(name="party-register")
@click.option(
    "--programs/--no-programs", default=True,
    help="Hae myös puolueiden yleisohjelmat (PDF) rekisteristä (oletus: kyllä)",
)
@click.option("--refresh", is_flag=True, help="Korvaa aiemmin haetut yleisohjelmat")
@click.option("--queue", "queue", is_flag=True, help="Run as background Celery task")
def party_register(programs: bool, refresh: bool, queue: bool):
    """Puolueet ja yleisohjelmat Oikeusministeriön puoluerekisteristä (puoluerekisteri.fi)."""
    if queue:
        _enqueue("ingest_party_register_task", programs=programs, refresh=refresh)
        return
    from vaalikone.ingest.harvesters import ingest_party_register

    asyncio.run(ingest_party_register(programs=programs, refresh=refresh))


@ingest.command(name="pohtiva")
@click.option("--party", "parties", multiple=True, help="Puolue (toistettava), esim. --party SDP")
@click.option("--since", default=2019, show_default=True, type=int, help="Vanhin vuosi")
@click.option("--until", default=None, type=int, help="Uusin vuosi")
@click.option(
    "--type", "types", multiple=True,
    type=click.Choice(
        ["vaaliohjelma", "yleisohjelma", "tavoiteohjelma", "erityisohjelma", "muu ohjelma"]
    ),
    help="Pohtivan ohjelmatyyppi (toistettava). Oletus: kaikki",
)
@click.option(
    "--lang", "languages", multiple=True, default=("fi",), show_default=True,
    help="Kielet (fi, sv, en; toistettava). Käännökset kaksinkertaistavat puolueen painon haussa",
)
@click.option("--max-per-party", default=None, type=int, help="Enintään N uusinta per puolue")
@click.option(
    "--delay", default=1.0, show_default=True, type=float, help="Viive pyyntöjen välissä (s)"
)
@click.option("--refresh", is_flag=True, help="Korvaa aiemmin Pohtivasta haetut dokumentit")
@click.option("--dry-run", is_flag=True, help="Listaa vain, älä hae tekstejä")
@click.option("--queue", "queue", is_flag=True, help="Run as background Celery task")
def pohtiva(
    parties: tuple[str, ...], since: int, until: int | None, types: tuple[str, ...],
    languages: tuple[str, ...], max_per_party: int | None, delay: float, refresh: bool,
    dry_run: bool, queue: bool,
):
    """Puolueohjelmat FSD:n Pohtiva-tietovarannosta (fsd.tuni.fi/pohtiva)."""
    kwargs = dict(
        parties=list(parties) or None, since=since, until=until, types=list(types) or None,
        languages=list(languages), max_per_party=max_per_party, refresh=refresh,
        delay=delay, dry_run=dry_run,
    )
    if queue:
        _enqueue("ingest_pohtiva_task", **kwargs)
        return
    from vaalikone.ingest.harvesters import ingest_pohtiva

    asyncio.run(ingest_pohtiva(**kwargs))
