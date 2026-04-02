from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from vaalikone.api.deps import get_db
from vaalikone.models.party import Party
from vaalikone.models.representative import Representative

router = APIRouter(prefix="/api/v1/representatives", tags=["representatives"])


@router.get("")
async def list_representatives(
    party: str | None = Query(None, description="Filter by party abbreviation"),
    db: AsyncSession = Depends(get_db),
):
    query = select(Representative)
    if party:
        query = query.join(Party).where(Party.abbreviation == party.upper())
    query = query.order_by(Representative.last_name)

    result = await db.execute(query)
    reps = result.scalars().all()
    return [
        {
            "id": str(r.id),
            "first_name": r.first_name,
            "last_name": r.last_name,
            "party_id": str(r.party_id) if r.party_id else None,
            "constituency": r.constituency,
            "elected_year": r.elected_year,
        }
        for r in reps
    ]
