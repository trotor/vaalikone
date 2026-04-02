from sqlalchemy import Text, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from vaalikone.models.base import Base, UUIDMixin


class Party(UUIDMixin, Base):
    __tablename__ = "parties"

    name: Mapped[str] = mapped_column(Text, nullable=False)
    abbreviation: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    founded: Mapped[int | None] = mapped_column(Integer)
    ideology: Mapped[str | None] = mapped_column(Text)
    website: Mapped[str | None] = mapped_column(Text)
    logo_url: Mapped[str | None] = mapped_column(Text)

    representatives = relationship("Representative", back_populates="party")
    sources = relationship("Source", back_populates="party")
    documents = relationship("Document", back_populates="party")
