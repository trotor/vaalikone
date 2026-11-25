import json

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from vaalikone.api.deps import get_db
from vaalikone.core.config import get_settings
from vaalikone.models.query_log import QueryLog
from vaalikone.query.hybrid_search import text_search
from vaalikone.query.pipeline import query as run_query
from vaalikone.query.pipeline import retrieve
from vaalikone.query.response import stream_response

router = APIRouter(prefix="/api/v1", tags=["query"])

TEXT_ONLY_MODEL = "__text_only__"


def _check_model_allowed(model: str) -> str:
    """Validate the requested chat model against the configured allowlist."""
    settings = get_settings()
    model = model.strip() if model else settings.DEFAULT_LLM_MODEL
    if not model:
        model = settings.DEFAULT_LLM_MODEL
    allowed = settings.allowed_chat_models
    if model not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"Model {model!r} not allowed. Allowed models: {allowed}",
        )
    return model


@router.get("/search")
async def search_documents(
    q: str = Query(..., description="Search query"),
    party: str | None = Query(None, description="Filter by party abbreviation"),
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    results = await text_search(db, q, limit=limit, party_filter=party)
    return {"query": q, "results": results, "count": len(results)}


@router.get("/compare")
async def compare_parties(
    q: str = Query(..., description="Topic to compare (e.g. 'metsäpolitiikka')"),
    limit_per_party: int = Query(3, ge=1, le=10),
    db: AsyncSession = Depends(get_db),
):
    """LLM-free party comparison: top source excerpts per party, straight from the DB.

    Returns {party: [{title, snippet, source_url, relevance, content_type}]}.
    No language model involved — pure retrieval, no hallucination risk.
    """
    results = await text_search(db, q, limit=limit_per_party * 20)
    by_party: dict[str, list[dict]] = {}
    for r in results:
        by_party.setdefault(r.get("party") or "muu", []).append(r)
    # Keep top N per party, sort parties by best relevance
    parties = {
        p: sorted(items, key=lambda x: x.get("relevance") or 0, reverse=True)[:limit_per_party]
        for p, items in by_party.items()
    }
    parties = dict(
        sorted(
            parties.items(),
            key=lambda kv: max((x.get("relevance") or 0) for x in kv[1]),
            reverse=True,
        )
    )
    return {"query": q, "parties": parties, "party_count": len(parties)}


class ChatRequest(BaseModel):
    question: str
    party: str | None = None
    model: str = ""
    use_semantic: bool = True


@router.post("/chat")
async def chat(request: ChatRequest, db: AsyncSession = Depends(get_db)):
    model = _check_model_allowed(request.model or get_settings().DEFAULT_LLM_MODEL)
    if model == TEXT_ONLY_MODEL:
        # Text-only mode — return search results without LLM
        results = await text_search(db, request.question, limit=10, party_filter=request.party)
        return {
            "answer": "\n\n".join(
                f"[{r.get('party', '?')}] {r.get('title', '')}\n{(r.get('snippet') or '')[:300]}"
                for r in results
            ) if results else "Ei hakutuloksia.",
            "sources": [
                {"party": r.get("party"), "title": r.get("title"), "url": r.get("source_url")}
                for r in results
            ],
            "model": "text-only",
        }
    result = await run_query(
        db,
        question=request.question,
        model=model,
        party_filter=request.party,
        use_semantic=request.use_semantic,
    )

    # Log the query
    try:
        log = QueryLog(
            query_text=request.question,
            response_text=(result.get("answer") or "")[:2000],
            model_used=model,
            tokens_used=result.get("tokens", {}).get("total"),
        )
        db.add(log)
        await db.commit()
    except Exception:
        await db.rollback()

    return result


@router.post("/chat/stream")
async def chat_stream(request: ChatRequest, db: AsyncSession = Depends(get_db)):
    """Chat with SSE streaming: emits chunk events, then a done event with sources."""
    model = _check_model_allowed(request.model or get_settings().DEFAULT_LLM_MODEL)

    async def event_generator():
        if model == TEXT_ONLY_MODEL:
            results = await text_search(db, request.question, limit=10, party_filter=request.party)
            answer = "\n\n".join(
                f"[{r.get('party', '?')}] {r.get('title', '')}\n{(r.get('snippet') or '')[:300]}"
                for r in results
            ) if results else "Ei hakutuloksia."
            yield f"data: {json.dumps({'type': 'chunk', 'text': answer}, ensure_ascii=False)}\n\n"
            done = {
                "type": "done", "answer": answer, "model": "text-only",
                "sources": [
                    {"party": r.get("party"), "title": r.get("title"), "url": r.get("source_url")}
                    for r in results
                ],
            }
            yield f"data: {json.dumps(done, ensure_ascii=False)}\n\n"
            return

        results = await retrieve(
            db,
            request.question,
            party_filter=request.party,
            use_semantic=request.use_semantic,
        )
        if not results:
            done = {
                "type": "done",
                "answer": "Valitettavasti en löytänyt tietokannasta vastausta kysymykseesi.",
                "model": model, "sources": [],
            }
            yield f"data: {json.dumps(done, ensure_ascii=False)}\n\n"
            return

        from vaalikone.query.pipeline import build_sources
        full_answer = ""
        async for event in stream_response(request.question, results, model=model):
            if event["type"] == "chunk":
                full_answer += event["text"]
            else:
                event["sources"] = build_sources(results)
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

        # Log the query
        try:
            log = QueryLog(
                query_text=request.question,
                response_text=full_answer[:2000],
                model_used=model,
            )
            db.add(log)
            await db.commit()
        except Exception:
            await db.rollback()

    return StreamingResponse(event_generator(), media_type="text/event-stream")


class SuggestRequest(BaseModel):
    question: str
    answer: str


# Pre-generated random question pool (filled lazily)
_random_question_pool: list[str] = []


async def _fill_random_pool(db: AsyncSession, count: int = 10):
    """Generate random questions from document chunks using a cheap model."""
    import os

    import litellm

    from vaalikone.models.document import Document
    from vaalikone.models.embedding import Embedding
    from vaalikone.models.party import Party

    settings = get_settings()
    if settings.OPENAI_API_KEY:
        os.environ.setdefault("OPENAI_API_KEY", settings.OPENAI_API_KEY)

    result = await db.execute(
        select(Embedding.chunk_text, Document.title, Party.abbreviation)
        .join(Document, Embedding.document_id == Document.id)
        .outerjoin(Party, Document.party_id == Party.id)
        .order_by(func.random())
        .limit(count)
    )
    chunks = result.all()

    for chunk_text, title, party in chunks:
        try:
            resp = await litellm.acompletion(
                model=get_settings().CHEAP_LLM_MODEL,
                messages=[{
                    "role": "user",
                    "content": (
                        f"Puolue: {party or '?'}, dokumentti: {title or ''}\n"
                        f"Teksti: {chunk_text[:400]}\n\n"
                        "Keksi 1 lyhyt kiinnostava kysymys suomalaisesta politiikasta "
                        "taman perusteella. Palauta VAIN kysymys."
                    ),
                }],
                max_tokens=50,
            )
            q = (resp.choices[0].message.content or "").strip().strip('"')
            if q and 10 < len(q) < 150 and "?" in q:
                _random_question_pool.append(q)
        except Exception:
            pass


@router.post("/suggest")
async def suggest_followups(request: SuggestRequest, db: AsyncSession = Depends(get_db)):
    """Return follow-up suggestions: 2 contextual + 1 random from pool."""
    import os
    import random

    import litellm
    settings = get_settings()
    if settings.OPENAI_API_KEY:
        os.environ.setdefault("OPENAI_API_KEY", settings.OPENAI_API_KEY)

    # Fill pool if empty (lazy init, runs once)
    if len(_random_question_pool) < 3:
        await _fill_random_pool(db, count=10)

    # Generate 2 contextual follow-ups
    contextual = []
    try:
        resp = await litellm.acompletion(
            model=get_settings().CHEAP_LLM_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Generoi 2 lyhyttä jatkokysymystä suomalaisesta politiikasta edellisen "
                        "kysymyksen ja vastauksen perusteella. Palauta VAIN 2 kysymystä, "
                        "yksi per rivi, "
                        "ilman numerointia tai muuta muotoilua. Suomeksi."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Kysymys: {request.question[:500]}\n"
                        f"Vastaus: {request.answer[:800]}"
                    ),
                },
            ],
            max_tokens=150,
        )
        text = resp.choices[0].message.content or ""
        contextual = [s.strip() for s in text.strip().split("\n") if s.strip()][:2]
    except Exception:
        pass

    # Pick 1 random from pool
    random_picks = []
    if _random_question_pool:
        pick = random.choice(_random_question_pool)
        random_picks = [pick]
        # Remove used question, refill if running low
        _random_question_pool.remove(pick)

    suggestions = contextual + random_picks
    return {"suggestions": suggestions[:3]}


DEFAULT_SUGGESTIONS = [
    "Mitä puolueet sanovat metsäkeskuksesta?",
    "Vertaa puolueiden veropolitiikkaa",
    "Miten puolueet suhtautuvat maahanmuuttoon?",
    "Mitä varjobudjeteissa sanotaan koulutuksesta?",
    "Mikä on liberaalipuolueen kanta ydinvoimaan?",
    "Mitä hallitusohjelmassa sanotaan terveydenhuollosta?",
    "Miten puolueet suhtautuvat NATO-jäsenyyteen?",
    "Vertaa oppositiopuolueiden vaihtoehtobudjetteja",
    "Mitä puolueet sanovat eläkejärjestelmästä?",
    "Miten puolueet haluavat kehittää perusturvaa?",
]


@router.get("/suggestions")
async def get_suggestions(db: AsyncSession = Depends(get_db)):
    """Question suggestions: recent queries, random chunk inspiration, and defaults."""
    import random

    from vaalikone.models.document import Document
    from vaalikone.models.embedding import Embedding
    from vaalikone.models.party import Party

    # Get recent unique questions
    result = await db.execute(
        select(QueryLog.query_text)
        .order_by(QueryLog.created_at.desc())
        .limit(50)
    )
    recent = list({row[0] for row in result.all()})

    # Pick a random chunk and generate a question from it using a cheap model
    random_question = None
    try:
        result = await db.execute(
            select(Embedding.chunk_text, Document.title, Party.abbreviation)
            .join(Document, Embedding.document_id == Document.id)
            .outerjoin(Party, Document.party_id == Party.id)
            .order_by(func.random())
            .limit(1)
        )
        row = result.first()
        if row:
            import os

            import litellm
            settings = get_settings()
            if settings.OPENAI_API_KEY:
                os.environ.setdefault("OPENAI_API_KEY", settings.OPENAI_API_KEY)
            resp = await litellm.acompletion(
                model=get_settings().CHEAP_LLM_MODEL,
                messages=[{
                    "role": "user",
                    "content": (
                        f"Lue tama teksti puolueelta {row[2] or '?'} ({row[1] or ''}):\n"
                        f"{row[0][:500]}\n\n"
                        "Keksi 1 lyhyt, kiinnostava kysymys suomalaisesta politiikasta "
                        "taman perusteella. Palauta VAIN kysymys, ei muuta."
                    ),
                }],
                max_tokens=60,
            )
            q = (resp.choices[0].message.content or "").strip().strip('"')
            if q and len(q) > 10:
                random_question = q
    except Exception:
        pass

    # Build suggestion pool
    pool = recent[:3]
    if random_question and random_question not in pool:
        pool.insert(0, random_question)

    defaults_shuffled = DEFAULT_SUGGESTIONS.copy()
    random.shuffle(defaults_shuffled)
    for d in defaults_shuffled:
        if d not in pool:
            pool.append(d)
        if len(pool) >= 6:
            break

    if len(recent) < 3:
        random.shuffle(pool)

    return {"suggestions": pool[:5]}


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
                                    headers={
                                        "Authorization": f"Bearer {settings.OPENAI_API_KEY or ''}"
                                    })
            if resp.status_code in (200, 401):  # 401 = reachable but bad key
                status["internet"] = True
            if resp.status_code == 200:
                status["openai"] = True
    except Exception:
        pass

    return status
