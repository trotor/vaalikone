import enum
import uuid
from datetime import datetime

from sqlalchemy import Enum, ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from vaalikone.models.base import Base, UUIDMixin


class ContentType(enum.StrEnum):
    VAALIOHJELMA = "vaaliohjelma"
    PUOLUEOHJELMA = "puolueohjelma"
    VARJOBUDJETTI = "varjobudjetti"
    HALLITUSOHJELMA = "hallitusohjelma"
    KUNTAVAALIOHJELMA = "kuntavaaliohjelma"
    BLOGIKIRJOITUS = "blogikirjoitus"
    SOME_POSTAUS = "some_postaus"
    PUHEENVUORO = "puheenvuoro"
    AANESTYS = "äänestys"
    KIRJALLINEN_KYSYMYS = "kirjallinen_kysymys"
    ALOITE = "aloite"
    MUU = "muu"


class Document(UUIDMixin, Base):
    __tablename__ = "documents"

    source_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sources.id"))
    party_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("parties.id"), nullable=True
    )
    representative_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("representatives.id"), nullable=True
    )
    title: Mapped[str | None] = mapped_column(Text)
    content_text: Mapped[str | None] = mapped_column(Text)
    content_type: Mapped[ContentType] = mapped_column(
        Enum(ContentType, native_enum=False), default=ContentType.MUU
    )
    published_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    language: Mapped[str] = mapped_column(Text, default="fi")
    ai_summary: Mapped[str | None] = mapped_column(Text)
    ai_topics: Mapped[dict | None] = mapped_column(JSONB)
    ai_sentiment: Mapped[str | None] = mapped_column(Text)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB)

    source = relationship("Source", back_populates="documents")
    party = relationship("Party", back_populates="documents")
    representative = relationship("Representative", back_populates="documents")
    embeddings = relationship("Embedding", back_populates="document")
