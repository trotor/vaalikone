from datetime import datetime

from sqlalchemy import Boolean, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from vaalikone.db.types import JSONType, TimestampType
from vaalikone.models.base import Base, UUIDMixin


class Voting(UUIDMixin, Base):
    """Täysistunnon äänestys (api.eduskunta.fi, kategoria ``aanestys``).

    Edustajakohtaiset äänet ovat ``votes``-taulussa: ``votes.subject == voting_id``.
    ``group_results`` lasketaan edustajakohtaisista äänistä eduskuntaryhmittäin
    (ryhmä äänestyshetkellä): ``{"kok": {"name", "party", "jaa", "ei", "tyhja",
    "poissa"}}``.
    """

    __tablename__ = "votings"

    voting_id: Mapped[str] = mapped_column(Text, unique=True, nullable=False)  # 2024-138-165
    session: Mapped[str | None] = mapped_column(Text)  # 2024-138
    year: Mapped[int | None] = mapped_column(Integer, index=True)
    number: Mapped[int | None] = mapped_column(Integer)
    voted_at: Mapped[datetime | None] = mapped_column(TimestampType())
    title: Mapped[str | None] = mapped_column(Text)  # äänestyksen otsikko
    item_title: Mapped[str | None] = mapped_column(Text)  # käsiteltävän asian otsikko
    stage: Mapped[str | None] = mapped_column(Text)  # käsittelyvaihe
    document_ref: Mapped[str | None] = mapped_column(Text)  # HE 109/2024 vp
    document_type: Mapped[str | None] = mapped_column(Text)  # HE, VK, KAA...
    cancelled: Mapped[bool] = mapped_column(Boolean, default=False)
    result: Mapped[dict | None] = mapped_column(JSONType())
    group_results: Mapped[dict | None] = mapped_column(JSONType())
    government_opposition: Mapped[dict | None] = mapped_column(JSONType())
