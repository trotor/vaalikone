import httpx
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from vaalikone.api.deps import get_db
from vaalikone.core.config import get_settings
from vaalikone.query.hybrid_search import text_search
from vaalikone.query.pipeline import query as run_query

router = APIRouter(prefix="/api/v1", tags=["query"])


@router.get("/search")
async def search_documents(
    q: str = Query(..., description="Search query"),
    party: str | None = Query(None, description="Filter by party abbreviation"),
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    results = await text_search(db, q, limit=limit, party_filter=party)
    return {"query": q, "results": results, "count": len(results)}


class ChatRequest(BaseModel):
    question: str
    party: str | None = None
    model: str = "gpt-4o-mini"
    use_semantic: bool = True


@router.post("/chat")
async def chat(request: ChatRequest, db: AsyncSession = Depends(get_db)):
    model = request.model.strip() if request.model else "gpt-4o-mini"
    if not model or model == "__text_only__":
        # Text-only mode — return search results without LLM
        results = await text_search(db, request.question, limit=10, party_filter=request.party)
        return {
            "answer": "\n\n".join(
                f"[{r.get('party', '?')}] {r.get('title', '')}\n{(r.get('snippet') or '')[:300]}"
                for r in results
            ) if results else "Ei hakutuloksia.",
            "sources": [{"party": r.get("party"), "title": r.get("title"), "url": r.get("source_url")} for r in results],
            "model": "text-only",
        }
    result = await run_query(
        db,
        question=request.question,
        model=model,
        party_filter=request.party,
        use_semantic=request.use_semantic,
    )
    return result


@router.get("/connectivity")
async def check_connectivity():
    """Check which services are available: OpenAI, Ollama, internet."""
    settings = get_settings()
    status = {
        "openai": False,
        "ollama": False,
        "internet": False,
        "ollama_models": [],
    }

    # Check Ollama
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            resp = await client.get("http://localhost:11434/api/tags")
            if resp.status_code == 200:
                status["ollama"] = True
                data = resp.json()
                # Filter: only text LLMs, not embedding or vision models
                skip = {"embed", "llava", "moondream", "bge", "mxbai", "nomic"}
                status["ollama_models"] = [
                    m["name"] for m in data.get("models", [])
                    if not any(s in m["name"].lower() for s in skip)
                ]
    except Exception:
        pass

    # Check internet (OpenAI)
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get("https://api.openai.com/v1/models",
                                    headers={"Authorization": f"Bearer {settings.OPENAI_API_KEY or ''}"})
            if resp.status_code in (200, 401):  # 401 = reachable but bad key
                status["internet"] = True
            if resp.status_code == 200:
                status["openai"] = True
    except Exception:
        pass

    return status
