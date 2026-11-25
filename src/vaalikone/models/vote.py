import enum
import uuid
from datetime import datetime

from sqlalchemy import Enum, ForeignKey, Text
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from vaalikone.models.base import Base, UUIDMixin


class VoteChoice(enum.StrEnum):
    JAA = "jaa"
    EI = "ei"
    TYHJA = "tyhjä"
    POISSA = "poissa"


class Vote(UUIDMixin, Base):
    __tablename__ = "votes"

    representative_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("representatives.id")
    )
    session: Mapped[str | None] = mapped_column(Text)
    subject: Mapped[str | None] = mapped_column(Text)
    subject_title: Mapped[str | None] = mapped_column(Text)
    vote: Mapped[VoteChoice] = mapped_column(Enum(VoteChoice, native_enum=False))
    voted_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    document_url: Mapped[str | None] = mapped_column(Text)

    representative = relationship("Representative", back_populates="votes")
