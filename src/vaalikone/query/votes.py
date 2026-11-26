"""Täysistuntoäänestysten haku aiheen perusteella (MCP ``party_votes``).

1. Tekstiosumat äänestysten otsikoista, asioista ja asiakirjatunnuksista
   (tarkka: "HE 315/2022", "Pohjois-Atlantin").
2. Jos tekstiosumia ei ole: semanttinen haku asiakohtaisista AANESTYS-dokumenteista
   (``ingest vote-documents``), jolloin "Nato" löytää Pohjois-Atlantin liittoa
   koskevat äänestykset. Dokumentin ``metadata.voting_ids`` johtaa takaisin ``votings``-riveihin.

Semanttisessa haussa verrataan vain dokumentin ensimmäistä pätkää (otsikko + alku):
myöhemmät pätkät ovat lähes pelkkiä ryhmien lukurivejä, jotka muistuttavat toisiaan ja
osuvat mihin tahansa lyhyeen hakuun. Mukaan otetaan asiat, joiden samankaltaisuus on
``RELATIVE_MARGIN``:n sisällä parhaasta.
"""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from vaalikone.models.document import ContentType, Document
from vaalikone.models.voting import Voting

DEFAULT_EMBED_MODEL = "ollama/bge-m3"
SEMANTIC_CANDIDATES = 30  # asioita (ensimmäisiä pätkiä), joista valitaan
RELATIVE_MARGIN = 0.04


@dataclass
class VotingHit:
    voting: Voting
    match: str  # "teksti" | "semanttinen"
    similarity: float | None = None


async def find_votings(
    session: AsyncSession,
    text: str,
    limit: int = 10,
    per_matter: int = 3,
    embed_model: str = DEFAULT_EMBED_MODEL,
) -> list[VotingHit]:
    """Tekstiosumat, tai jos niitä ei ole, semanttisesti lähimmät asiat. Kustakin asiasta
    uusimmat ``per_matter`` äänestystä. Ilman embedding-palvelua vain tekstiosumat."""
    from vaalikone.query.hybrid_search import escape_ilike

    pattern = f"%{escape_ilike(text)}%"
    exact = (await session.execute(
        select(Voting)
        .where(
            Voting.item_title.ilike(pattern, escape="\\")
            | Voting.title.ilike(pattern, escape="\\")
            | Voting.document_ref.ilike(pattern, escape="\\")
        )
        .where(Voting.cancelled.is_(False))
        .order_by(Voting.voted_at.desc().nullslast(), Voting.number.desc())
        .limit(500)
    )).scalars().all()
    hits, per = [], {}
    for v in exact:  # enintään per_matter uusinta äänestystä asiaa kohden
        key = (v.document_ref, v.item_title)
        if per.get(key, 0) < per_matter:
            per[key] = per.get(key, 0) + 1
            hits.append(VotingHit(v, "teksti"))
    if hits:  # tarkat osumat riittävät; semanttinen täyttö toisi vain sivuosumia
        return hits[:limit]

    try:
        from vaalikone.ingest.embedder import get_embedding
        from vaalikone.query.hybrid_search import semantic_search

        vec = await get_embedding(text, model=embed_model)
        chunks = await semantic_search(
            session, vec, limit=SEMANTIC_CANDIDATES, embed_model=embed_model,
            content_type=ContentType.AANESTYS, chunk_index=0,
        )
    except Exception:
        return hits  # ei Ollamaa / embeddingejä: pelkät tekstiosumat

    best: dict[str, float] = {}  # document_id -> samankaltaisuus, järjestys säilyy
    top = chunks[0]["similarity"] if chunks else 0.0
    for c in chunks:
        if c["similarity"] >= top - RELATIVE_MARGIN:
            best.setdefault(c["document_id"], c["similarity"])
    if not best:
        return hits
    import uuid

    metas = dict((await session.execute(
        select(Document.id, Document.metadata_)
        .where(Document.id.in_([uuid.UUID(d) for d in best]))
    )).all())
    wanted: list[tuple[str, float]] = []
    for doc_id, sim in best.items():
        ids = ((metas.get(uuid.UUID(doc_id)) or {}).get("voting_ids") or [])
        wanted.extend((vid, sim) for vid in list(reversed(ids))[:per_matter])

    seen = {h.voting.voting_id for h in hits}
    wanted = [(vid, sim) for vid, sim in wanted if vid not in seen]
    rows = {v.voting_id: v for v in (await session.execute(
        select(Voting).where(Voting.voting_id.in_([vid for vid, _ in wanted]))
    )).scalars()}
    for vid, sim in wanted:
        if len(hits) >= limit:
            break
        if vid in rows and not rows[vid].cancelled:
            hits.append(VotingHit(rows[vid], "semanttinen", sim))
    return hits
