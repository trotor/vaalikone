import uuid

from sqlalchemy import text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from vaalikone.db.types import GUID


class Base(DeclarativeBase):
    pass


class UUIDMixin:
    id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
