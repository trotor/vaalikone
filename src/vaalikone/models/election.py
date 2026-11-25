import enum

from sqlalchemy import Enum, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from vaalikone.models.base import Base, UUIDMixin


class ElectionType(enum.StrEnum):
    EDUSKUNTAVAALIT = "eduskuntavaalit"
    KUNTAVAALIT = "kuntavaalit"
    EUROPARLAMENTTIVAALIT = "europarlamenttivaalit"
    PRESIDENTINVAALI = "presidentinvaali"


class Election(UUIDMixin, Base):
    __tablename__ = "elections"

    year: Mapped[int] = mapped_column(Integer, nullable=False)
    election_type: Mapped[ElectionType] = mapped_column(
        Enum(ElectionType, native_enum=False), default=ElectionType.EDUSKUNTAVAALIT
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[str | None] = mapped_column(Text)

    candidates = relationship("Candidate", back_populates="election")
