from datetime import datetime

from sqlalchemy import Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from vaalikone.db.types import TimestampType
from vaalikone.models.base import Base, UUIDMixin


class QueryLog(UUIDMixin, Base):
    __tablename__ = "query_log"

    user_id: Mapped[str | None] = mapped_column(Text)
    query_text: Mapped[str] = mapped_column(Text)
    response_text: Mapped[str | None] = mapped_column(Text)
    model_used: Mapped[str | None] = mapped_column(Text)
    tokens_used: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        TimestampType(), server_default="now()"
    )
