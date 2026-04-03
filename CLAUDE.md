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

# Run server
uvicorn vaalikone.api.app:app --host 0.0.0.0 --port 8003

# CLI
vaalikone --help
```

## Architecture

This is a RAG (Retrieval-Augmented Generation) system for Finnish political data. It ingests party programs, shadow budgets, parliamentary votes, and MP data, then answers questions via hybrid search (text + semantic) backed by LLM.

### Data flow

```
Ingest: URL/PDF/API → connectors → AI filter → chunking → embedding → PostgreSQL+pgvector
Query:  Question → hybrid search (FTS + vector) → context assembly → LLM → answer with sources
```

### Key layers

- **`src/vaalikone/models/`** — SQLAlchemy 2.0 async models. All use `UUIDMixin` from `base.py`. The `Embedding` table uses `pgvector` with flexible dimensions (no fixed size) to support multiple embedding models.

- **`src/vaalikone/ingest/`** — Data ingestion pipeline. `connectors/` has source-specific fetchers (eduskunta API, web/trafilatura, PDF/PyMuPDF, recursive crawler). `pipeline.py` orchestrates chunk→embed→store with per-document commits to isolate failures. `embedder.py` routes to OpenAI (via LiteLLM) or Ollama (direct httpx calls — LiteLLM's Ollama embedding support is broken).

- **`src/vaalikone/query/`** — Query pipeline. `hybrid_search.py` combines PostgreSQL FTS (`plainto_tsquery('finnish', ...)`) with an ILIKE fallback for Finnish compound words the tokenizer misses, plus pgvector cosine similarity. `pipeline.py` merges text results (exact matches first) with semantic results, deduplicates, then passes to `response.py` for LLM generation.

- **`src/vaalikone/api/`** — FastAPI app. `deps.py` provides `get_db` dependency. `routes/query.py` has both search and chat endpoints plus a `/connectivity` endpoint that probes OpenAI and Ollama availability. `static/index.html` is a self-contained chat UI that auto-detects available models.

- **`src/vaalikone/cli/`** — Click CLI registered as `vaalikone` entrypoint. Each file is a command group or standalone command.

### Configuration

All config via `.env` file, loaded by `pydantic-settings` in `core/config.py`. The `OPENAI_API_KEY` is explicitly propagated to `os.environ` in `embedder.py` and `response.py` because LiteLLM doesn't read `.env` files.

### Database

PostgreSQL 16 + pgvector on port **5435** (offset +3 to avoid conflicts). Test database `vaalikone_test` is auto-created by `docker/postgres/init.sql`. Tests use `conftest.py` fixtures that create/drop tables per session.

### Embedding model compatibility

The `embeddings` table uses `Vector()` (no dimension constraint). When switching models, you must: `DELETE FROM embeddings`, optionally `ALTER TABLE embeddings ALTER COLUMN embedding TYPE vector(N)` for performance, then re-embed with `--force`.

### Finnish language considerations

- PostgreSQL FTS uses `'finnish'` dictionary but fails on compound words (e.g., "Metsäkeskuslain" when searching "metsäkeskus"). The ILIKE fallback in `hybrid_search.py` catches these.
- Local embedding models (nomic-embed-text) have weak Finnish support. OpenAI `text-embedding-3-small` or local `bge-m3` work much better for Finnish.

### Crawler

`connectors/crawler.py` follows internal links up to configurable depth. Uses keyword heuristics to filter political content, with optional LLM-based relevance check via Ollama. Only follows `<a href>` tags (not `<link>` CSS/font refs).
