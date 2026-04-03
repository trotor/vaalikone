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

    # Search for relevant context
    if use_semantic:
        query_vec = await get_embedding(question, model=embed_model)
        results = await semantic_search(session, query_vec, limit=limit, party_filter=party_filter)
    else:
        results = await text_search(session, question, limit=limit, party_filter=party_filter)

    if not results:
        return {
            "answer": "Valitettavasti en löytänyt tietokannasta vastausta kysymykseesi.",
            "sources": [],
            "model": model,
        }

    # Generate response
    answer = await generate_response(question, results, model=model)

    # Deduplicate sources
    seen = set()
    sources = []
    for r in results:
        key = (r.get("party"), r.get("title"))
        if key not in seen:
            seen.add(key)
            sources.append({"party": r.get("party"), "title": r.get("title")})

    return {
        "answer": answer,
        "sources": sources,
        "model": model,
    }
