import enum
import uuid
from datetime import datetime

from sqlalchemy import Enum, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from vaalikone.db.types import GUID, JSONType, TimestampType
from vaalikone.models.base import Base, UUIDMixin


class ContentType(enum.StrEnum):
    VAALIOHJELMA = "vaaliohjelma"
    PUOLUEOHJELMA = "puolueohjelma"
    VARJOBUDJETTI = "varjobudjetti"
    HALLITUSOHJELMA = "hallitusohjelma"
    KUNTAVAALIOHJELMA = "kuntavaaliohjelma"
    EUROVAALIOHJELMA = "eurovaaliohjelma"
    BLOGIKIRJOITUS = "blogikirjoitus"
    SOME_POSTAUS = "some_postaus"
    PUHEENVUORO = "puheenvuoro"
    AANESTYS = "äänestys"
    KIRJALLINEN_KYSYMYS = "kirjallinen_kysymys"
    ALOITE = "aloite"
    MUU = "muu"


class Document(UUIDMixin, Base):
    __tablename__ = "documents"

    source_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("sources.id"))
    party_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("parties.id"), nullable=True
    )
    representative_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("representatives.id"), nullable=True
    )
    title: Mapped[str | None] = mapped_column(Text)
    content_text: Mapped[str | None] = mapped_column(Text)
    content_type: Mapped[ContentType] = mapped_column(
        Enum(ContentType, native_enum=False), default=ContentType.MUU
    )
    published_at: Mapped[datetime | None] = mapped_column(TimestampType())
    language: Mapped[str] = mapped_column(Text, default="fi")
    ai_summary: Mapped[str | None] = mapped_column(Text)
    ai_topics: Mapped[dict | None] = mapped_column(JSONType())
    ai_sentiment: Mapped[str | None] = mapped_column(Text)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONType())

    source = relationship("Source", back_populates="documents")
    party = relationship("Party", back_populates="documents")
    representative = relationship("Representative", back_populates="documents")
    embeddings = relationship("Embedding", back_populates="document")
