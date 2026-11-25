import uuid

from sqlalchemy import Boolean, Float, ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from vaalikone.db.types import GUID
from vaalikone.models.base import Base, UUIDMixin


class Candidate(UUIDMixin, Base):
    __tablename__ = "candidates"

    election_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("elections.id"), nullable=False
    )
    party_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("parties.id"), nullable=True
    )
    # Ehdokkaan numero (vaalit.fi / Tilastokeskus)
    candidate_number: Mapped[str | None] = mapped_column(Text)
    first_name: Mapped[str] = mapped_column(Text, nullable=False)
    last_name: Mapped[str] = mapped_column(Text, nullable=False)
    constituency: Mapped[str | None] = mapped_column(Text)
    votes: Mapped[int | None] = mapped_column(Integer)
    vote_share: Mapped[float | None] = mapped_column(Float)
    comparison_number: Mapped[float | None] = mapped_column(Float)
    elected: Mapped[bool] = mapped_column(Boolean, default=False)

    election = relationship("Election", back_populates="candidates")
    party = relationship("Party")
