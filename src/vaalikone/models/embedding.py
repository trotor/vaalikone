import uuid

from sqlalchemy import ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from vaalikone.db.types import GUID, VectorType
from vaalikone.models.base import Base, UUIDMixin


class Embedding(UUIDMixin, Base):
    __tablename__ = "embeddings"

    document_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("documents.id"))
    chunk_index: Mapped[int] = mapped_column(Integer)
    chunk_text: Mapped[str] = mapped_column(Text)
    embedding = mapped_column(VectorType())
    model_name: Mapped[str] = mapped_column(Text)

    document = relationship("Document", back_populates="embeddings")
