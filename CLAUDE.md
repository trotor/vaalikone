# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Fresh Environment Setup (for AI agents)

Run these commands in order to set up a new development environment:

```bash
# 1. Install dependencies
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# 2. Start database
docker compose up -d postgres redis
sleep 5  # wait for healthy

# 3. Configure
cp .env.example .env
# Edit .env: add OPENAI_API_KEY if available

# 4. Run migrations
alembic upgrade head

# 5. Load existing data (if dump exists)
gunzip -k data/vaalikone-dump.sql.gz
docker exec -i $(docker ps -qf "name=postgres") psql -U vaalikone < data/vaalikone-dump.sql

# 6. OR seed fresh data
vaalikone seed parties
vaalikone ingest representatives
vaalikone ingest votes --max-pages 50
vaalikone ingest embed --model ollama/bge-m3

# 7. Install Ollama models (macOS)
# brew install ollama  # or download from https://ollama.com/download
ollama pull bge-m3              # embedding (1.2 GB) — required for semantic search
ollama pull llama3.2:3b         # LLM (2 GB) — lightweight, fast
ollama pull deepseek-r1:14b     # LLM (9 GB) — reasoning, needs 16+ GB RAM

# 8. Start server
uvicorn vaalikone.api.app:app --host 0.0.0.0 --port 8003
```

## Common Commands

```bash
# Tests (requires running PostgreSQL on port 5435)
python -m pytest tests/ -v
python -m pytest tests/test_api.py::test_health -v

# Lint
ruff check src/ tests/

# Migrations
alembic upgrade head
alembic revision --autogenerate -m "description"

# Server (must run from project root for .env)
uvicorn vaalikone.api.app:app --host 0.0.0.0 --port 8003

# Data ingestion
vaalikone ingest url <URL> --party SDP
vaalikone ingest pdf <URL> --party PS
vaalikone ingest crawl <URL> --party VIHR --depth 2 --max-pages 50
vaalikone ingest embed --model ollama/bge-m3

# Queries
vaalikone search "verotus"
vaalikone chat "Vertaa puolueiden ilmastopolitiikkaa"
vaalikone stats
vaalikone documents
vaalikone compare-embeddings
```

## Architecture

RAG system for Finnish political data. Ingests party programs, shadow budgets, parliamentary votes, and MP data, then answers questions via hybrid search backed by LLM.

### Data flow

```
Ingest: URL/PDF/API/crawl -> connectors -> chunking -> embedding -> PostgreSQL+pgvector
Query:  Question -> hybrid search (FTS + ILIKE + vector) -> context assembly -> LLM -> answer with sources
```

### Key layers

- **`models/`** — SQLAlchemy 2.0 async. All use `UUIDMixin` from `base.py`. `Embedding` uses `pgvector` with flexible dimensions (`Vector()`) to support multiple embedding models simultaneously.

- **`ingest/`** — Ingestion pipeline. `connectors/` has eduskunta API, web/trafilatura, PDF/PyMuPDF, recursive crawler. `pipeline.py` orchestrates chunk->embed->store with per-document commits and isolated sessions. `embedder.py` routes to OpenAI (via LiteLLM) or Ollama (direct httpx — LiteLLM's Ollama embedding is broken).

- **`query/`** — `hybrid_search.py` combines PostgreSQL FTS (`plainto_tsquery('finnish', ...)`) with ILIKE fallback for compound words, plus pgvector cosine similarity filtered by `model_name`. `pipeline.py` merges text + semantic results, deduplicates, passes to `response.py` for LLM generation. Response includes cost/token tracking.

- **`api/`** — FastAPI app. `routes/query.py` has search, chat, suggest, suggestions, connectivity endpoints. `static/index.html` is self-contained chat UI with auto model detection. All queries logged to `query_log` table.

- **`cli/`** — Click CLI as `vaalikone` entrypoint. Each file is a command registered in `main.py`.

### Configuration

`.env` loaded by pydantic-settings in `core/config.py`. `OPENAI_API_KEY` is explicitly propagated to `os.environ` in `embedder.py` and `response.py` because LiteLLM doesn't read `.env`.

### Database

PostgreSQL 16 + pgvector on port **5435** (all ports +3: Redis 6382, Keycloak 8083, API 8003). Test DB `vaalikone_test` auto-created by `docker/postgres/init.sql`.

### Multi-model embeddings

Multiple models coexist via `model_name` column. `semantic_search()` filters by `embed_model`. Best model for Finnish: `ollama/bge-m3` (benchmark: 0.578 avg, 12/15 wins, 11/16 parties found).

### Finnish language gotchas

- FTS misses compound words ("Metsäkeskuslain" vs "metsäkeskus"). ILIKE fallback catches these. ILIKE-only hits get baseline relevance 0.01.
- bge-m3 is best for Finnish embeddings. nomic-embed-text is weak for Finnish.
- Crawler uses Finnish political keyword heuristics with optional LLM relevance check.

### Known security issues (pre-production)

- No authentication on API. Add API key auth or Keycloak before public deployment.
- Model parameter not validated — add allowlist in `routes/query.py`.
- SSRF risk in URL connectors — validate URLs before fetching.
- ILIKE wildcard injection — escape `%` and `_` in queries.
- Docker ports bound to 0.0.0.0 — bind to 127.0.0.1 for non-public.
- Hardcoded DB credentials in docker-compose.yml.
- Dockerfile runs as root.
