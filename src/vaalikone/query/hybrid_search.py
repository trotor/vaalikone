from sqlalchemy import func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from vaalikone.db.types import VectorType
from vaalikone.models.document import Document
from vaalikone.models.embedding import Embedding
from vaalikone.models.party import Party
from vaalikone.models.source import Source


def escape_ilike(value: str) -> str:
    """Escape ILIKE/LIKE wildcards (%, _, \\) so user input is matched literally."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _dialect_name(session: AsyncSession) -> str:
    bind = session.bind
    return bind.dialect.name if bind is not None else "postgresql"


async def _rows_to_results(rows) -> list[dict]:
    results = []
    for row in rows:
        relevance = float(row.relevance) if row.relevance else 0.0
        if row.ilike_hit and relevance == 0.0:
            relevance = 0.01  # small but non-zero so LIKE-only hits are not always last
        results.append({
            "document_id": str(row.id),
            "title": row.title,
            "content_type": row.content_type.value if row.content_type else None,
            "party": row.party,
            "source_url": row.source_url,
            "relevance": relevance,
            "snippet": row.snippet,
        })
    return results


async def _text_search_sql(
    session: AsyncSession, query: str, limit: int, party_filter: str | None
) -> list[dict]:
    """SQLite: lower() LIKE + esiintymämäärään perustuva relevanssi + instr-snippet."""
    q = query.lower()
    content_l = func.lower(Document.content_text)
    like_pattern = f"%{escape_ilike(q)}%"
    like_match = content_l.like(like_pattern, escape="\\")
    occurrences = (
        func.length(content_l) - func.length(func.replace(content_l, q, ""))
    ) / func.nullif(func.length(q), 0)
    pos = func.instr(content_l, q)
    snippet = func.concat(
        text("'...'"),
        func.substr(Document.content_text, func.max(1, pos - 100), 300 + func.length(query)),
        text("'...'"),
    )
    stmt = (
        select(
            Document.id, Document.title, Document.content_type,
            Party.abbreviation.label("party"), Source.url.label("source_url"),
            func.coalesce(occurrences, 0.0).label("relevance"),
            snippet.label("snippet"), like_match.label("ilike_hit"),
        )
        .outerjoin(Party, Document.party_id == Party.id)
        .outerjoin(Source, Document.source_id == Source.id)
        .where(like_match)
    )
    if party_filter:
        stmt = stmt.where(Party.abbreviation == party_filter.upper())
    stmt = stmt.order_by(func.coalesce(occurrences, 0.0).desc()).limit(limit)
    return await _rows_to_results((await session.execute(stmt)).all())


async def _text_search_pg(
    session: AsyncSession, query: str, limit: int, party_filter: str | None
) -> list[dict]:
    """PostgreSQL: ts_vector (suomen stemmaus) + ILIKE + ts_headline-snippet."""
    ts_query = func.plainto_tsquery("finnish", query)
    ts_vector = func.to_tsvector("finnish", Document.content_text)
    ts_rank = func.ts_rank(ts_vector, ts_query)
    ilike_match = Document.content_text.ilike(f"%{escape_ilike(query)}%", escape="\\")
    ts_match = ts_vector.op("@@")(ts_query)
    pos = func.position(func.lower(query).op("IN")(func.lower(Document.content_text)))
    snippet_fallback = func.concat(
        text("'...'"),
        func.substring(
            Document.content_text, func.greatest(1, pos - 100), 300 + func.length(query)
        ),
        text("'...'"),
    )
    snippet = func.coalesce(
        func.nullif(
            func.ts_headline("finnish", Document.content_text, ts_query,
                             text("'MaxFragments=3, MaxWords=40, MinWords=20'")),
            "",
        ),
        snippet_fallback,
    )
    stmt = (
        select(
            Document.id, Document.title, Document.content_type,
            Party.abbreviation.label("party"), Source.url.label("source_url"),
            ts_rank.label("relevance"), snippet.label("snippet"),
            ilike_match.label("ilike_hit"),
        )
        .outerjoin(Party, Document.party_id == Party.id)
        .outerjoin(Source, Document.source_id == Source.id)
        .where(or_(ts_match, ilike_match))
    )
    if party_filter:
        stmt = stmt.where(Party.abbreviation == party_filter.upper())
    stmt = stmt.order_by(ts_rank.desc()).limit(limit)
    return await _rows_to_results((await session.execute(stmt)).all())


async def text_search(
    session: AsyncSession,
    query: str,
    limit: int = 10,
    party_filter: str | None = None,
) -> list[dict]:
    """Hybrid full-text + LIKE search across documents.

    PostgreSQL: ts_vector (Finnish stemming) + ILIKE fallback + ts_headline snippet.
    SQLite: lower() LIKE with occurrence ranking; falls back to a stem-truncated
    query ("metsä" -> "metsä" ... "mets") since LIKE does not stem Finnish.
    """
    if _dialect_name(session) == "sqlite":
        results = await _text_search_sql(session, query, limit, party_filter)
        if len(query) > 4:
            # LIKE ei stemmaa suomea: lisää myös kantasana (metsä -> mets)
            stem = await _text_search_sql(session, query[:-1], limit, party_filter)
            seen = {r["document_id"] for r in results}
            for r in stem:
                if r["document_id"] not in seen:
                    r["relevance"] = (r["relevance"] or 0) * 0.5  # stem-osumat alemmaksi
                    results.append(r)
            results.sort(key=lambda r: r["relevance"], reverse=True)
            results = results[:limit]
        return results
    return await _text_search_pg(session, query, limit, party_filter)


async def semantic_search(
    session: AsyncSession,
    query_embedding: list[float],
    limit: int = 10,
    party_filter: str | None = None,
    embed_model: str | None = None,
    content_type=None,
    chunk_index: int | None = None,
) -> list[dict]:
    """Semantic similarity search (optionally limited to one ContentType).

    PostgreSQL: pgvector cosine distance (<=>). SQLite: sqlite-vec
    vec_distance_cosine on the float32 BLOB column.
    """
    if _dialect_name(session) == "sqlite":
        from sqlalchemy import cast

        distance = func.vec_distance_cosine(
            Embedding.embedding, cast(query_embedding, VectorType())
        )
    else:
        distance = Embedding.embedding.cosine_distance(query_embedding)

    stmt = (
        select(
            Embedding.chunk_text,
            Embedding.chunk_index,
            Document.id.label("document_id"),
            Document.title,
            Document.content_type,
            Party.abbreviation.label("party"),
            Source.url.label("source_url"),
            distance.label("distance"),
        )
        .join(Document, Embedding.document_id == Document.id)
        .outerjoin(Party, Document.party_id == Party.id)
        .outerjoin(Source, Document.source_id == Source.id)
    )

    # Filter by embedding model to avoid dimension mismatches
    if embed_model:
        stmt = stmt.where(Embedding.model_name == embed_model)

    if party_filter:
        stmt = stmt.where(Party.abbreviation == party_filter.upper())
    if content_type is not None:
        stmt = stmt.where(Document.content_type == content_type)
    if chunk_index is not None:
        stmt = stmt.where(Embedding.chunk_index == chunk_index)

    stmt = stmt.order_by(distance).limit(limit)

    result = await session.execute(stmt)
    rows = result.all()

    return [
        {
            "chunk_text": row.chunk_text,
            "document_id": str(row.document_id),
            "title": row.title,
            "content_type": row.content_type.value if row.content_type else None,
            "party": row.party,
            "source_url": row.source_url,
            "similarity": 1.0 - float(row.distance),
        }
        for row in rows
    ]
