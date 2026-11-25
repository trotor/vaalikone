import uuid

from sqlalchemy import ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from vaalikone.db.types import GUID, JSONType
from vaalikone.models.base import Base, UUIDMixin


class Representative(UUIDMixin, Base):
    __tablename__ = "representatives"

    party_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("parties.id"), nullable=True
    )
    # Eduskunnan avoimen datan henkilonumero (MemberOfParliament.personId) — stable id for dedup
    person_id: Mapped[str | None] = mapped_column(Text, unique=True)
    first_name: Mapped[str] = mapped_column(Text, nullable=False)
    last_name: Mapped[str] = mapped_column(Text, nullable=False)
    constituency: Mapped[str | None] = mapped_column(Text)
    elected_year: Mapped[int | None] = mapped_column(Integer)
    birth_year: Mapped[int | None] = mapped_column(Integer)
    email: Mapped[str | None] = mapped_column(Text)
    website: Mapped[str | None] = mapped_column(Text)
    photo_url: Mapped[str | None] = mapped_column(Text)
    social_media: Mapped[dict | None] = mapped_column(JSONType())

    party = relationship("Party", back_populates="representatives")
    votes = relationship("Vote", back_populates="representative")
    sources = relationship("Source", back_populates="representative")
    documents = relationship("Document", back_populates="representative")
