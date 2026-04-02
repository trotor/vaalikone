from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from vaalikone.api.deps import get_db
from vaalikone.models.party import Party

router = APIRouter(prefix="/api/v1/parties", tags=["parties"])


@router.get("")
async def list_parties(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Party).order_by(Party.abbreviation))
    parties = result.scalars().all()
    return [
        {
            "id": str(p.id),
            "name": p.name,
            "abbreviation": p.abbreviation,
            "website": p.website,
            "ideology": p.ideology,
            "founded": p.founded,
        }
        for p in parties
    ]
