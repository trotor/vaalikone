from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import AsyncSession

from vaalikone.models.document import Document
from vaalikone.models.embedding import Embedding
from vaalikone.models.party import Party
from vaalikone.models.source import Source


async def text_search(
    session: AsyncSession,
    query: str,
    limit: int = 10,
    party_filter: str | None = None,
) -> list[dict]:
    """Hybrid full-text + ILIKE search across documents.
    Uses PostgreSQL ts_vector for Finnish stemming, with ILIKE fallback
    for compound words that the Finnish tokenizer misses."""

    # Strategy: ts_vector search + ILIKE fallback for compound words
    ts_query = func.plainto_tsquery("finnish", query)
    ts_vector = func.to_tsvector("finnish", Document.content_text)
    ts_rank = func.ts_rank(ts_vector, ts_query)

    # ILIKE catches compound words (e.g. "metsäkeskuslain" for "metsäkeskus")
    ilike_pattern = f"%{query}%"
    ilike_match = Document.content_text.ilike(ilike_pattern)

    # Combined: ts_vector match OR ilike match
    ts_match = ts_vector.op("@@")(ts_query)

    stmt = (
        select(
            Document.id,
            Document.title,
            Document.content_type,
            Party.abbreviation.label("party"),
            Source.url.label("source_url"),
            ts_rank.label("relevance"),
            func.ts_headline(
                "finnish",
                Document.content_text,
                ts_query,
                text("'MaxFragments=3, MaxWords=40, MinWords=20'"),
            ).label("snippet"),
            ilike_match.label("ilike_hit"),
        )
        .outerjoin(Party, Document.party_id == Party.id)
        .outerjoin(Source, Document.source_id == Source.id)
        .where(ts_match | ilike_match)
    )

    if party_filter:
        stmt = stmt.where(Party.abbreviation == party_filter.upper())

    stmt = stmt.order_by(ts_rank.desc()).limit(limit)

    result = await session.execute(stmt)
    rows = result.all()

    results = []
    for row in rows:
        snippet = row.snippet
        # For ilike-only hits, snippet from ts_headline may be empty/irrelevant
        # We'll fix snippets in a second pass below

        results.append({
            "document_id": str(row.id),
            "title": row.title,
            "content_type": row.content_type.value if row.content_type else None,
            "party": row.party,
            "source_url": row.source_url,
            "relevance": float(row.relevance) if row.relevance else 0.0,
            "snippet": snippet,
        })

    # Fix snippets for ILIKE-only hits
    for r in results:
        if r["snippet"] and query.lower() in r["snippet"].lower():
            continue
        doc_result = await session.execute(
            select(Document.content_text).where(Document.id == r["document_id"])
        )
        content = doc_result.scalar_one_or_none()
        if content:
            idx = content.lower().find(query.lower())
            if idx >= 0:
                start = max(0, idx - 100)
                end = min(len(content), idx + len(query) + 200)
                r["snippet"] = "..." + content[start:end] + "..."

    return results


async def text_search_with_snippets(
    session: AsyncSession,
    query: str,
    limit: int = 10,
    party_filter: str | None = None,
) -> list[dict]:
    """Like text_search but with better snippet extraction for ILIKE hits."""
    results = await text_search(session, query, limit=limit, party_filter=party_filter)

    # For results with poor snippets, fetch content and extract manually
    for r in results:
        if r["snippet"] and query.lower() not in r["snippet"].lower():
            doc_result = await session.execute(
                select(Document.content_text).where(Document.id == r["document_id"])
            )
            content = doc_result.scalar_one_or_none()
            if content:
                idx = content.lower().find(query.lower())
                if idx >= 0:
                    start = max(0, idx - 100)
                    end = min(len(content), idx + len(query) + 200)
                    r["snippet"] = "..." + content[start:end] + "..."

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

    from pgvector.sqlalchemy import Vector

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
