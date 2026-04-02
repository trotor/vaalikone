from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from vaalikone.api.deps import get_db
from vaalikone.models.source import Source

router = APIRouter(prefix="/api/v1/sources", tags=["sources"])


@router.get("")
async def list_sources(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Source).order_by(Source.fetched_at.desc().nulls_last()))
    sources = result.scalars().all()
    return [
        {
            "id": str(s.id),
            "source_type": s.source_type.value,
            "url": s.url,
            "title": s.title,
            "status": s.status.value,
            "fetched_at": s.fetched_at.isoformat() if s.fetched_at else None,
        }
        for s in sources
    ]


@router.get("/stats")
async def source_stats(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Source.source_type, Source.status, func.count(Source.id))
        .group_by(Source.source_type, Source.status)
    )
    rows = result.all()
    return [
        {"source_type": st.value, "status": status.value, "count": count}
        for st, status, count in rows
    ]
