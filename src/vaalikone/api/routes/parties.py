from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from vaalikone.api.deps import get_db
from vaalikone.models.document import Document
from vaalikone.models.party import Party
from vaalikone.models.representative import Representative
from vaalikone.models.vote import Vote

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


@router.get("/{abbreviation}")
async def get_party(abbreviation: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Party).where(Party.abbreviation == abbreviation.upper())
    )
    party = result.scalar_one_or_none()
    if not party:
        raise HTTPException(status_code=404, detail="Party not found")

    doc_count = await db.execute(
        select(func.count()).select_from(Document).where(Document.party_id == party.id)
    )
    rep_count = await db.execute(
        select(func.count()).select_from(Representative).where(Representative.party_id == party.id)
    )
    vote_count = await db.execute(
        select(func.count()).select_from(Vote)
        .join(Representative)
        .where(Representative.party_id == party.id)
    )

    return {
        "id": str(party.id),
        "name": party.name,
        "abbreviation": party.abbreviation,
        "website": party.website,
        "ideology": party.ideology,
        "founded": party.founded,
        "documents": doc_count.scalar(),
        "representatives": rep_count.scalar(),
        "votes": vote_count.scalar(),
    }
