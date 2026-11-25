import uuid

from pgvector.sqlalchemy import Vector
from sqlalchemy import ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from vaalikone.models.base import Base, UUIDMixin


class Embedding(UUIDMixin, Base):
    __tablename__ = "embeddings"

    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("documents.id"))
    chunk_index: Mapped[int] = mapped_column(Integer)
    chunk_text: Mapped[str] = mapped_column(Text)
    embedding = mapped_column(Vector())
    model_name: Mapped[str] = mapped_column(Text)

    document = relationship("Document", back_populates="embeddings")
