import enum
import uuid
from datetime import datetime

from sqlalchemy import Enum, ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from vaalikone.models.base import Base, UUIDMixin


class SourceType(enum.StrEnum):
    WEBSITE = "website"
    PDF = "pdf"
    SOCIAL_MEDIA = "social_media"
    API = "api"
    MANUAL = "manual"


class SourceStatus(enum.StrEnum):
    PENDING = "pending"
    INDEXED = "indexed"
    FAILED = "failed"


class Source(UUIDMixin, Base):
    __tablename__ = "sources"

    source_type: Mapped[SourceType] = mapped_column(Enum(SourceType, native_enum=False))
    url: Mapped[str | None] = mapped_column(Text)
    title: Mapped[str | None] = mapped_column(Text)
    fetched_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    status: Mapped[SourceStatus] = mapped_column(
        Enum(SourceStatus, native_enum=False), default=SourceStatus.PENDING
    )
    party_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("parties.id"), nullable=True
    )
    representative_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("representatives.id"), nullable=True
    )
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB)

    party = relationship("Party", back_populates="sources")
    representative = relationship("Representative", back_populates="sources")
    documents = relationship("Document", back_populates="source")
