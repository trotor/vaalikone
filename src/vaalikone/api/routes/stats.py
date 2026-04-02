from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from vaalikone.api.deps import get_db
from vaalikone.models.party import Party
from vaalikone.models.representative import Representative
from vaalikone.models.source import Source
from vaalikone.models.document import Document
from vaalikone.models.embedding import Embedding
from vaalikone.models.vote import Vote

router = APIRouter(prefix="/api/v1/stats", tags=["stats"])


@router.get("")
async def get_stats(db: AsyncSession = Depends(get_db)):
    counts = {}
    for name, model in [
        ("parties", Party),
        ("representatives", Representative),
        ("sources", Source),
        ("documents", Document),
        ("embeddings", Embedding),
        ("votes", Vote),
    ]:
        result = await db.execute(select(func.count()).select_from(model))
        counts[name] = result.scalar()

    counts["total_data_points"] = sum(counts.values())
    return counts
