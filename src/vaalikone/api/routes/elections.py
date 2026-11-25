from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from vaalikone.api.deps import get_db
from vaalikone.models.candidate import Candidate
from vaalikone.models.election import Election
from vaalikone.models.party import Party

router = APIRouter(prefix="/api/v1", tags=["elections"])


@router.get("/elections")
async def list_elections(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Election).order_by(Election.year.desc()))
    elections = result.scalars().all()
    return [
        {
            "id": str(e.id),
            "year": e.year,
            "election_type": e.election_type.value,
            "name": e.name,
            "source_url": e.source_url,
        }
        for e in elections
    ]


@router.get("/elections/{election_id}/candidates")
async def list_candidates(
    election_id: str,
    party: str | None = Query(None, description="Filter by party abbreviation"),
    elected_only: bool = Query(False, description="Only elected candidates"),
    q: str | None = Query(None, description="Search by candidate name"),
    limit: int = Query(100, ge=1, le=2000),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(
            Candidate.id,
            Candidate.candidate_number,
            Candidate.first_name,
            Candidate.last_name,
            Candidate.constituency,
            Candidate.votes,
            Candidate.vote_share,
            Candidate.comparison_number,
            Candidate.elected,
            Party.abbreviation.label("party"),
        )
        .outerjoin(Party, Candidate.party_id == Party.id)
        .where(Candidate.election_id == election_id)
    )
    if party:
        stmt = stmt.where(Party.abbreviation == party.upper())
    if elected_only:
        stmt = stmt.where(Candidate.elected.is_(True))
    if q:
        from vaalikone.query.hybrid_search import escape_ilike

        stmt = stmt.where(
            (Candidate.first_name + " " + Candidate.last_name).ilike(
                f"%{escape_ilike(q)}%", escape="\\"
            )
        )
    stmt = stmt.order_by(Candidate.votes.desc().nullslast()).limit(limit)

    result = await db.execute(stmt)
    rows = result.all()
    return {
        "candidates": [
            {
                "id": str(r.id),
                "candidate_number": r.candidate_number,
                "name": f"{r.first_name} {r.last_name}",
                "party": r.party,
                "constituency": r.constituency,
                "votes": r.votes,
                "vote_share": r.vote_share,
                "comparison_number": r.comparison_number,
                "elected": r.elected,
            }
            for r in rows
        ],
        "count": len(rows),
    }


@router.get("/elections/{election_id}/stats")
async def election_stats(election_id: str, db: AsyncSession = Depends(get_db)):
    """Per-party candidate/vote/elected stats for an election."""
    stmt = (
        select(
            Party.abbreviation.label("party"),
            func.count(Candidate.id).label("candidates"),
            func.sum(Candidate.votes).label("votes"),
            func.count().filter(Candidate.elected.is_(True)).label("elected"),
        )
        .outerjoin(Party, Candidate.party_id == Party.id)
        .where(Candidate.election_id == election_id)
        .group_by(Party.abbreviation)
        .order_by(func.sum(Candidate.votes).desc().nullslast())
    )
    result = await db.execute(stmt)
    rows = result.all()
    return {
        "parties": [
            {
                "party": r.party or "Muut",
                "candidates": r.candidates,
                "votes": int(r.votes or 0),
                "elected": r.elected,
            }
            for r in rows
        ]
    }
