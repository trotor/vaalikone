import uuid

from sqlalchemy import Text, Integer, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from vaalikone.models.base import Base, UUIDMixin


class Representative(UUIDMixin, Base):
    __tablename__ = "representatives"

    party_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("parties.id"))
    first_name: Mapped[str] = mapped_column(Text, nullable=False)
    last_name: Mapped[str] = mapped_column(Text, nullable=False)
    constituency: Mapped[str | None] = mapped_column(Text)
    elected_year: Mapped[int | None] = mapped_column(Integer)
    birth_year: Mapped[int | None] = mapped_column(Integer)
    email: Mapped[str | None] = mapped_column(Text)
    website: Mapped[str | None] = mapped_column(Text)
    photo_url: Mapped[str | None] = mapped_column(Text)
    social_media: Mapped[dict | None] = mapped_column(JSONB)

    party = relationship("Party", back_populates="representatives")
    votes = relationship("Vote", back_populates="representative")
    sources = relationship("Source", back_populates="representative")
    documents = relationship("Document", back_populates="representative")
