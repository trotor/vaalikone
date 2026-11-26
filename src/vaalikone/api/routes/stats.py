from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from vaalikone.api.deps import get_db
from vaalikone.core.config import is_read_only
from vaalikone.models.candidate import Candidate
from vaalikone.models.document import Document
from vaalikone.models.election import Election
from vaalikone.models.embedding import Embedding
from vaalikone.models.party import Party
from vaalikone.models.representative import Representative
from vaalikone.models.source import Source
from vaalikone.models.vote import Vote
from vaalikone.models.voting import Voting

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
        ("votings", Voting),
        ("votes", Vote),
        ("elections", Election),
        ("candidates", Candidate),
    ]:
        result = await db.execute(select(func.count()).select_from(model))
        counts[name] = result.scalar()

    counts["total_data_points"] = sum(counts.values())
    counts["read_only"] = is_read_only()
    return counts
