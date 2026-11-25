"""add campaign_finances table

Revision ID: a1b2c3d4e5f6
Revises: 2914d0e98982
Create Date: 2026-04-05 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: str | Sequence[str] | None = "2914d0e98982"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "campaign_finances",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("election_id", sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("elections.id"), nullable=True),
        sa.Column("party_id", sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("parties.id"), nullable=True),
        sa.Column("recipient_first_name", sa.Text(), nullable=True),
        sa.Column("recipient_last_name", sa.Text(), nullable=True),
        sa.Column("constituency", sa.Text(), nullable=True),
        sa.Column("donor_name", sa.Text(), nullable=True),
        sa.Column("donor_business_id", sa.Text(), nullable=True),
        sa.Column("donor_first_names", sa.Text(), nullable=True),
        sa.Column("donor_last_name", sa.Text(), nullable=True),
        sa.Column("donor_municipality", sa.Text(), nullable=True),
        sa.Column("form_numbers", sa.Text(), nullable=True),
        sa.Column("loan_name", sa.Text(), nullable=True),
        sa.Column("loan_term", sa.Text(), nullable=True),
        sa.Column("amount", sa.Float(), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_campaign_finances_election_id", "campaign_finances", ["election_id"])
    op.create_index("ix_campaign_finances_party_id", "campaign_finances", ["party_id"])
    op.create_index("ix_campaign_finances_recipient", "campaign_finances",
                    ["recipient_last_name", "recipient_first_name"])


def downgrade() -> None:
    op.drop_index("ix_campaign_finances_recipient", table_name="campaign_finances")
    op.drop_index("ix_campaign_finances_party_id", table_name="campaign_finances")
    op.drop_index("ix_campaign_finances_election_id", table_name="campaign_finances")
    op.drop_table("campaign_finances")
