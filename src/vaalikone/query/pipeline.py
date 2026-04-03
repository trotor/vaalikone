from sqlalchemy.ext.asyncio import AsyncSession

from vaalikone.query.hybrid_search import text_search, semantic_search
from vaalikone.query.response import generate_response
from vaalikone.ingest.embedder import get_embedding


async def query(
    session: AsyncSession,
    question: str,
    model: str = "gpt-4o",
    embed_model: str = "text-embedding-3-small",
    party_filter: str | None = None,
    use_semantic: bool = False,
    limit: int = 10,
) -> dict:
    """Run a query through the pipeline: search -> generate response."""

    # Hybrid search: combine text search and semantic search for best results
    text_results = await text_search(session, question, limit=limit, party_filter=party_filter)

    semantic_results = []
    if use_semantic:
        try:
            query_vec = await get_embedding(question, model=embed_model)
            semantic_results = await semantic_search(
                session, query_vec, limit=limit, party_filter=party_filter,
                embed_model=embed_model,
            )
        except Exception:
            pass  # Fall back to text-only if embedding fails

    # Merge: text results first (exact matches), then semantic (conceptual matches)
    seen_docs = set()
    results = []
    for r in text_results:
        key = r.get("document_id")
        if key not in seen_docs:
            seen_docs.add(key)
            results.append(r)
    for r in semantic_results:
        key = r.get("document_id")
        if key not in seen_docs:
            seen_docs.add(key)
            results.append(r)
    results = results[:limit]

    if not results:
        return {
            "answer": "Valitettavasti en löytänyt tietokannasta vastausta kysymykseesi.",
            "sources": [],
            "model": model,
        }

    # Generate response
    answer = await generate_response(question, results, model=model)

    # Deduplicate sources with URLs
    seen = set()
    sources = []
    for r in results:
        key = (r.get("party"), r.get("title"))
        if key not in seen:
            seen.add(key)
            sources.append({
                "party": r.get("party"),
                "title": r.get("title"),
                "url": r.get("source_url"),
            })

    return {
        "answer": answer,
        "sources": sources,
        "model": model,
    }
