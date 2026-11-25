from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from vaalikone.api.deps import get_db
from vaalikone.models.party import Party
from vaalikone.models.representative import Representative
from vaalikone.models.vote import Vote

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


@router.get("/{rep_id}/votes")
async def list_representative_votes(
    rep_id: str,
    limit: int = Query(100, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
):
    """Voting history of a representative, with vote subject titles when available."""
    query = (
        select(Vote)
        .where(Vote.representative_id == rep_id)
        .order_by(Vote.voted_at.desc().nullslast(), Vote.session.desc().nullslast())
        .limit(limit)
    )
    result = await db.execute(query)
    votes = result.scalars().all()
    return [
        {
            "id": str(v.id),
            "session": v.session,
            "subject": v.subject,
            "subject_title": v.subject_title,
            "vote": v.vote.value,
            "voted_at": v.voted_at.isoformat() if v.voted_at else None,
            "document_url": v.document_url,
        }
        for v in votes
    ]
