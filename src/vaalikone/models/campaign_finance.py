import uuid
from datetime import datetime

from sqlalchemy import Float, ForeignKey, Text
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from vaalikone.models.base import Base, UUIDMixin


class CampaignFinance(UUIDMixin, Base):
    """Vaalirahoitusrivi (yksittäinen tuki/lahjoitus ehdokkaalle).

    Lähde: vaalirahoitusvalvonta.fi:n tutkittavat aineistot (CSV).
    """

    __tablename__ = "campaign_finances"

    election_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("elections.id"), nullable=True
    )
    party_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("parties.id"), nullable=True
    )
    recipient_first_name: Mapped[str | None] = mapped_column(Text)
    recipient_last_name: Mapped[str | None] = mapped_column(Text)
    constituency: Mapped[str | None] = mapped_column(Text)
    donor_name: Mapped[str | None] = mapped_column(Text)
    donor_business_id: Mapped[str | None] = mapped_column(Text)
    donor_first_names: Mapped[str | None] = mapped_column(Text)
    donor_last_name: Mapped[str | None] = mapped_column(Text)
    donor_municipality: Mapped[str | None] = mapped_column(Text)
    form_numbers: Mapped[str | None] = mapped_column(Text)
    loan_name: Mapped[str | None] = mapped_column(Text)
    loan_term: Mapped[str | None] = mapped_column(Text)
    amount: Mapped[float | None] = mapped_column(Float)
    source_url: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default="now()"
    )

    election = relationship("Election")
    party = relationship("Party")
