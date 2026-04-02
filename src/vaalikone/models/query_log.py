from datetime import datetime

from sqlalchemy import Text, Integer
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column

from vaalikone.models.base import Base, UUIDMixin


class QueryLog(UUIDMixin, Base):
    __tablename__ = "query_log"

    user_id: Mapped[str | None] = mapped_column(Text)
    query_text: Mapped[str] = mapped_column(Text)
    response_text: Mapped[str | None] = mapped_column(Text)
    model_used: Mapped[str | None] = mapped_column(Text)
    tokens_used: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default="now()"
    )
