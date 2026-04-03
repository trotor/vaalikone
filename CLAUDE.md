# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Build & Run Commands

```bash
# Install (editable with dev deps)
pip install -e ".[dev]"

# Database (must be running for most operations)
docker compose up -d postgres redis

# Migrations
alembic upgrade head                              # apply
alembic revision --autogenerate -m "description"  # create new

# Tests (requires running PostgreSQL on port 5435)
python -m pytest tests/ -v                        # all tests
python -m pytest tests/test_api.py -v             # single file
python -m pytest tests/test_api.py::test_health -v  # single test

# Lint
ruff check src/ tests/
ruff check --fix src/ tests/

# Run server (must run from project root so .env is found)
uvicorn vaalikone.api.app:app --host 0.0.0.0 --port 8003

# CLI
vaalikone --help
vaalikone stats                     # database overview
vaalikone documents                 # documents per party
vaalikone search "verotus"          # text search
vaalikone chat "Vertaa puolueiden ilmastopolitiikkaa"  # AI chat
vaalikone ingest crawl <URL> --party SDP --depth 2     # recursive crawl
vaalikone ingest embed --model ollama/bge-m3           # generate embeddings
vaalikone compare-embeddings        # compare embedding model quality
```

## Architecture

RAG (Retrieval-Augmented Generation) system for Finnish political data. Ingests party programs, shadow budgets, parliamentary votes, and MP data, then answers questions via hybrid search (text + semantic) backed by LLM.

### Data flow

```
Ingest: URL/PDF/API/crawl → connectors → chunking → embedding → PostgreSQL+pgvector
Query:  Question → hybrid search (FTS + ILIKE + vector) → context assembly → LLM → answer with sources
```

### Key layers

- **`src/vaalikone/models/`** — SQLAlchemy 2.0 async models. All use `UUIDMixin` from `base.py`. The `Embedding` table uses `pgvector` with flexible dimensions (`Vector()`, no fixed size) to support multiple embedding models simultaneously.

- **`src/vaalikone/ingest/`** — Data ingestion pipeline. `connectors/` has source-specific fetchers (eduskunta API, web/trafilatura, PDF/PyMuPDF, recursive crawler). `pipeline.py` orchestrates chunk→embed→store with per-document commits and isolated sessions to prevent greenlet errors from cascading. `embedder.py` routes to OpenAI (via LiteLLM) or Ollama (direct httpx calls to `/api/embeddings` — LiteLLM's Ollama embedding integration is broken).

- **`src/vaalikone/query/`** — Query pipeline. `hybrid_search.py` combines PostgreSQL FTS (`plainto_tsquery('finnish', ...)`) with an ILIKE fallback for Finnish compound words, plus pgvector cosine similarity filtered by `model_name`. `pipeline.py` merges text results (exact matches first) with semantic results, deduplicates by document_id, then passes to `response.py` for LLM generation.

- **`src/vaalikone/api/`** — FastAPI app. `routes/query.py` has search, chat, and connectivity endpoints. `static/index.html` is a self-contained chat UI that auto-detects available models (OpenAI + Ollama) and falls back to text-only search when offline.

- **`src/vaalikone/cli/`** — Click CLI registered as `vaalikone` entrypoint. Each file is a command group or standalone command registered in `main.py`.

### Configuration

All config via `.env` file, loaded by `pydantic-settings` in `core/config.py`. The `OPENAI_API_KEY` is explicitly propagated to `os.environ` in `embedder.py` and `response.py` because LiteLLM doesn't read `.env` files. Server must be started from project root directory for `.env` to be found.

### Database

PostgreSQL 16 + pgvector on port **5435** (all ports offset +3 to avoid conflicts: Redis 6382, Keycloak 8083, API 8003). Test database `vaalikone_test` is auto-created by `docker/postgres/init.sql`. Tests use `conftest.py` fixtures that create/drop tables per session.

### Multi-model embedding support

Multiple embedding models coexist in the `embeddings` table, differentiated by `model_name` column. The `semantic_search()` function filters by `embed_model` parameter to avoid dimension mismatches. The `Vector()` column has no fixed dimension — when switching to a single model, you can add a dimension constraint for performance: `ALTER TABLE embeddings ALTER COLUMN embedding TYPE vector(N)`.

Current models: `text-embedding-3-small` (OpenAI, 1536d), `ollama/bge-m3` (1024d), `ollama/zembed-1` (2560d). Use `vaalikone compare-embeddings` to evaluate quality.

### Finnish language considerations

- PostgreSQL FTS uses `'finnish'` dictionary but fails on compound words (e.g., "Metsäkeskuslain" when searching "metsäkeskus"). The ILIKE fallback in `hybrid_search.py` catches these.
- Embedding model quality for Finnish varies significantly. OpenAI `text-embedding-3-small` and local `bge-m3` work well. `nomic-embed-text` has weak Finnish support.
- The recursive crawler (`connectors/crawler.py`) uses Finnish political keyword heuristics to filter relevant content, with optional LLM-based relevance check via Ollama.

### Source tracking

Every ingested document links back to a `Source` record with URL, title, source_type (website/pdf/api/manual), and party association. Use `vaalikone sources list` to audit provenance. The crawler skips already-indexed URLs via `Source.url` deduplication.
