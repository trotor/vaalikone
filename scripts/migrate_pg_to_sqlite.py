"""Siirtää datan PostgreSQL:stä SQLiteen (tai toisin päin) ORM-mallien kautta.

Käyttö:
    PG_URL=postgresql+asyncpg://vaalikone:vaalikone@localhost:5435/vaalikone \
        .venv/bin/python scripts/migrate_pg_to_sqlite.py

Kohde tulee .env:n DATABASE_URL:stä (oletus sqlite+aiosqlite:///./vaalikone.db).
"""

import asyncio
import os
import sys

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from vaalikone.core.config import get_settings
from vaalikone.db.engine import create_db_engine
from vaalikone.models import (
    Base,
    CampaignFinance,
    Candidate,
    Document,
    Election,
    Embedding,
    Party,
    QueryLog,
    Representative,
    Source,
    Vote,
)

PG_URL = os.environ.get("PG_URL")
MODELS = [Party, Representative, Source, Document, Embedding,
          Election, Candidate, CampaignFinance, Vote, QueryLog]


async def main() -> None:
    if not PG_URL:
        sys.exit("Aseta PG_URL (postgresql+asyncpg://...)")
    settings = get_settings()
    src_engine = create_db_engine(PG_URL)
    dst_engine = create_db_engine(settings.DATABASE_URL)

    async with dst_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    src = async_sessionmaker(src_engine, class_=AsyncSession, expire_on_commit=False)
    dst = async_sessionmaker(dst_engine, class_=AsyncSession, expire_on_commit=False)

    async with src() as s, dst() as d:
        for model in MODELS:
            rows = (await s.execute(select(model))).scalars().all()
            table = model.__tablename__
            await d.execute(model.__table__.delete())
            for r in rows:
                d.add(model(**{c.key: getattr(r, c.key) for c in model.__table__.columns}))
            await d.commit()
            print(f"  {table}: {len(rows)}")

    await src_engine.dispose()
    await dst_engine.dispose()
    print("Valmis.")


if __name__ == "__main__":
    asyncio.run(main())
