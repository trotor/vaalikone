from sqlalchemy.ext.asyncio import AsyncSession

from vaalikone.ingest.embedder import get_embedding
from vaalikone.query.hybrid_search import semantic_search, text_search
from vaalikone.query.response import generate_response


async def retrieve(
    session: AsyncSession,
    question: str,
    embed_model: str = "ollama/bge-m3",
    party_filter: str | None = None,
    use_semantic: bool = False,
    limit: int = 10,
) -> list[dict]:
    """Hybrid search: combine text search and semantic search, deduplicated.

    Returns a list of result dicts (document_id, title, party, source_url,
    relevance, snippet, ...).
    """
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
    return results[:limit]


def build_sources(results: list[dict]) -> list[dict]:
    """Deduplicated source list (party, title, url) from search results."""
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
    return sources


async def query(
    session: AsyncSession,
    question: str,
    model: str = "gpt-4o",
    embed_model: str = "ollama/bge-m3",
    party_filter: str | None = None,
    use_semantic: bool = False,
    limit: int = 10,
) -> dict:
    """Run a query through the pipeline: search -> generate response."""

    results = await retrieve(
        session,
        question,
        embed_model=embed_model,
        party_filter=party_filter,
        use_semantic=use_semantic,
        limit=limit,
    )

    if not results:
        return {
            "answer": "Valitettavasti en löytänyt tietokannasta vastausta kysymykseesi.",
            "sources": [],
            "model": model,
        }

    # Generate response
    llm_result = await generate_response(question, results, model=model)

    return {
        "answer": llm_result["text"],
        "sources": build_sources(results),
        "model": model,
        "cost": llm_result["cost"],
        "tokens": llm_result["tokens"],
    }
