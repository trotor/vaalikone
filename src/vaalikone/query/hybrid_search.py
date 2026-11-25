from sqlalchemy import func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from vaalikone.models.document import Document
from vaalikone.models.embedding import Embedding
from vaalikone.models.party import Party
from vaalikone.models.source import Source


def escape_ilike(value: str) -> str:
    """Escape ILIKE wildcards (%, _, \\) so user input is matched literally."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


async def text_search(
    session: AsyncSession,
    query: str,
    limit: int = 10,
    party_filter: str | None = None,
) -> list[dict]:
    """Hybrid full-text + ILIKE search across documents.
    Uses PostgreSQL ts_vector for Finnish stemming, with ILIKE fallback
    for compound words that the Finnish tokenizer misses.

    Snippets are computed in SQL (ts_headline, or a substring window around
    the ILIKE match) to avoid a per-row N+1 query.
    """
    ts_query = func.plainto_tsquery("finnish", query)
    ts_vector = func.to_tsvector("finnish", Document.content_text)
    ts_rank = func.ts_rank(ts_vector, ts_query)

    # ILIKE catches compound words (e.g. "metsäkeskuslain" for "metsäkeskus").
    # Wildcards in user input are escaped to prevent pattern injection.
    ilike_pattern = f"%{escape_ilike(query)}%"
    ilike_match = Document.content_text.ilike(ilike_pattern, escape="\\")

    ts_match = ts_vector.op("@@")(ts_query)

    # Position of the (case-insensitive) query in the content, for snippet extraction
    pos = func.position(func.lower(query).op("IN")(func.lower(Document.content_text)))
    snippet_fallback = func.concat(
        text("'...'"),
        func.substring(
            Document.content_text,
            func.greatest(1, pos - 100),
            300 + func.length(query),
        ),
        text("'...'"),
    )
    snippet = func.coalesce(
        func.nullif(
            func.ts_headline(
                "finnish",
                Document.content_text,
                ts_query,
                text("'MaxFragments=3, MaxWords=40, MinWords=20'"),
            ),
            "",
        ),
        snippet_fallback,
    )

    stmt = (
        select(
            Document.id,
            Document.title,
            Document.content_type,
            Party.abbreviation.label("party"),
            Source.url.label("source_url"),
            ts_rank.label("relevance"),
            snippet.label("snippet"),
            ilike_match.label("ilike_hit"),
        )
        .outerjoin(Party, Document.party_id == Party.id)
        .outerjoin(Source, Document.source_id == Source.id)
        .where(or_(ts_match, ilike_match))
    )

    if party_filter:
        stmt = stmt.where(Party.abbreviation == party_filter.upper())

    stmt = stmt.order_by(ts_rank.desc()).limit(limit)

    result = await session.execute(stmt)
    rows = result.all()

    results = []
    for row in rows:
        relevance = float(row.relevance) if row.relevance else 0.0
        if row.ilike_hit and relevance == 0.0:
            relevance = 0.01  # small but non-zero so ILIKE-only hits are not always last

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


async def semantic_search(
    session: AsyncSession,
    query_embedding: list[float],
    limit: int = 10,
    party_filter: str | None = None,
    embed_model: str | None = None,
) -> list[dict]:
    """Semantic similarity search using pgvector.
    Requires embeddings to be generated first.
    Filters by embed_model to avoid mixing different dimension embeddings."""

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
