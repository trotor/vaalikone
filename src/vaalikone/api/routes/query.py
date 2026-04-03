from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from vaalikone.api.deps import get_db
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
    result = await run_query(
        db,
        question=request.question,
        model=request.model,
        party_filter=request.party,
        use_semantic=request.use_semantic,
    )
    return result
