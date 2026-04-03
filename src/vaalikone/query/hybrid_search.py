from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import AsyncSession

from vaalikone.models.document import Document
from vaalikone.models.embedding import Embedding
from vaalikone.models.party import Party


async def text_search(
    session: AsyncSession,
    query: str,
    limit: int = 10,
    party_filter: str | None = None,
) -> list[dict]:
    """Full-text search across documents using PostgreSQL ts_vector.
    Works without embeddings."""

    # Use plainto_tsquery for simple Finnish text search
    ts_query = func.plainto_tsquery("finnish", query)
    ts_vector = func.to_tsvector("finnish", Document.content_text)
    rank = func.ts_rank(ts_vector, ts_query)

    stmt = (
        select(
            Document.id,
            Document.title,
            Document.content_type,
            Party.abbreviation.label("party"),
            rank.label("relevance"),
            func.ts_headline(
                "finnish",
                Document.content_text,
                ts_query,
                text("'MaxFragments=3, MaxWords=40, MinWords=20'"),
            ).label("snippet"),
        )
        .outerjoin(Party, Document.party_id == Party.id)
        .where(ts_vector.op("@@")(ts_query))
    )

    if party_filter:
        stmt = stmt.where(Party.abbreviation == party_filter.upper())

    stmt = stmt.order_by(rank.desc()).limit(limit)

    result = await session.execute(stmt)
    rows = result.all()

    return [
        {
            "document_id": str(row.id),
            "title": row.title,
            "content_type": row.content_type.value if row.content_type else None,
            "party": row.party,
            "relevance": float(row.relevance),
            "snippet": row.snippet,
        }
        for row in rows
    ]


async def semantic_search(
    session: AsyncSession,
    query_embedding: list[float],
    limit: int = 10,
    party_filter: str | None = None,
) -> list[dict]:
    """Semantic similarity search using pgvector.
    Requires embeddings to be generated first."""

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
            distance.label("distance"),
        )
        .join(Document, Embedding.document_id == Document.id)
        .outerjoin(Party, Document.party_id == Party.id)
    )

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
            "similarity": 1.0 - float(row.distance),
        }
        for row in rows
    ]
