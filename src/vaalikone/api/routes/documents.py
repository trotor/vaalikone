from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from vaalikone.api.deps import get_db
from vaalikone.models.document import Document
from vaalikone.models.party import Party

router = APIRouter(prefix="/api/v1/documents", tags=["documents"])


@router.get("")
async def list_documents(
    party: str | None = Query(None, description="Filter by party abbreviation"),
    db: AsyncSession = Depends(get_db),
):
    query = select(Document).outerjoin(Party, Document.party_id == Party.id)
    if party:
        query = query.where(Party.abbreviation == party.upper())
    query = query.order_by(Document.title)

    result = await db.execute(query)
    docs = result.scalars().all()
    return [
        {
            "id": str(d.id),
            "title": d.title,
            "content_type": d.content_type.value if d.content_type else None,
            "party_id": str(d.party_id) if d.party_id else None,
            "language": d.language,
            "content_length": len(d.content_text) if d.content_text else 0,
            "published_at": d.published_at.isoformat() if d.published_at else None,
        }
        for d in docs
    ]
