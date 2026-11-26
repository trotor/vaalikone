"""Celery tasks for background ingestion.

Run with: celery -A vaalikone.workers.tasks worker --loglevel=info
(enabled via `docker compose up worker`)
"""

import asyncio

from vaalikone.workers.celery_app import app


@app.task(bind=True, max_retries=3)
def ingest_url_task(self, url: str, party: str | None = None):
    from vaalikone.cli.ingest import _ingest_url

    try:
        asyncio.run(_ingest_url(url, party))
        return {"status": "ok", "url": url}
    except Exception as e:
        raise self.retry(exc=e, countdown=30)


@app.task(bind=True, max_retries=3)
def ingest_pdf_task(self, url: str, party: str | None = None, title: str | None = None):
    from vaalikone.cli.ingest import _ingest_pdf

    try:
        asyncio.run(_ingest_pdf(url, party, title))
        return {"status": "ok", "url": url}
    except Exception as e:
        raise self.retry(exc=e, countdown=30)


@app.task(bind=True, max_retries=3)
def ingest_crawl_task(
    self, seed_url: str, party: str | None = None, depth: int = 2,
    max_pages: int = 50, use_llm: bool = False,
):
    from vaalikone.cli.ingest import _ingest_crawl

    try:
        asyncio.run(_ingest_crawl(seed_url, party, depth, max_pages, use_llm))
        return {"status": "ok", "url": seed_url}
    except Exception as e:
        raise self.retry(exc=e, countdown=60)


@app.task(bind=True, max_retries=2)
def ingest_representatives_task(self):
    from vaalikone.cli.ingest import _ingest_representatives

    try:
        return asyncio.run(_ingest_representatives())
    except Exception as e:
        raise self.retry(exc=e, countdown=60)


@app.task(bind=True, max_retries=2)
def ingest_votes_task(self, max_pages: int | None = None):
    from vaalikone.cli.ingest import _ingest_votes

    try:
        return asyncio.run(_ingest_votes(max_pages))
    except Exception as e:
        raise self.retry(exc=e, countdown=60)


@app.task(bind=True, max_retries=2)
def ingest_vote_subjects_task(self, max_pages: int | None = None):
    from vaalikone.cli.ingest import _ingest_vote_subjects

    try:
        return asyncio.run(_ingest_vote_subjects(max_pages))
    except Exception as e:
        raise self.retry(exc=e, countdown=60)


@app.task(bind=True, max_retries=2)
def ingest_speeches_task(self, query: str, max_results: int = 100, start_from: int = 0):
    from vaalikone.cli.ingest import _ingest_speeches

    try:
        return asyncio.run(_ingest_speeches(query, max_results, start_from))
    except Exception as e:
        raise self.retry(exc=e, countdown=60)


@app.task(bind=True, max_retries=2)
def ingest_questions_task(
    self, max_results: int = 100, start_from: int = 0, valtiopaiva: str | None = None
):
    from vaalikone.cli.ingest import _ingest_questions

    try:
        return asyncio.run(_ingest_questions(max_results, start_from, valtiopaiva))
    except Exception as e:
        raise self.retry(exc=e, countdown=60)


@app.task(bind=True, max_retries=2)
def ingest_candidates_task(self, year: int = 2023, election: str = "eduskuntavaalit"):
    from vaalikone.cli.ingest import _ingest_candidates

    try:
        return asyncio.run(_ingest_candidates(year, election))
    except Exception as e:
        raise self.retry(exc=e, countdown=60)


@app.task(bind=True, max_retries=2)
def ingest_programs_task(
    self, party_filter: str | None = None, kind_filter: str | None = None, refresh: bool = False,
):
    from vaalikone.cli.ingest import _ingest_programs

    try:
        return asyncio.run(_ingest_programs(party_filter, kind_filter, refresh=refresh))
    except Exception as e:
        raise self.retry(exc=e, countdown=60)


@app.task(bind=True, max_retries=2)
def ingest_party_register_task(self, programs: bool = True, refresh: bool = False):
    from vaalikone.ingest.harvesters import ingest_party_register

    try:
        return asyncio.run(ingest_party_register(programs=programs, refresh=refresh))
    except Exception as e:
        raise self.retry(exc=e, countdown=60)


@app.task(bind=True, max_retries=2)
def ingest_pohtiva_task(self, **kwargs):
    from vaalikone.ingest.harvesters import ingest_pohtiva

    try:
        return asyncio.run(ingest_pohtiva(**kwargs))
    except Exception as e:
        raise self.retry(exc=e, countdown=60)


@app.task
def ingest_embed_task(model: str | None = None, force: bool = False):
    from vaalikone.cli.ingest import _ingest_embed

    return asyncio.run(_ingest_embed(model, force))
