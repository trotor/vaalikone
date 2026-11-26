"""add votings table (api.eduskunta.fi aanestys)

Revision ID: b7e1c2d3f4a5
Revises: a1b2c3d4e5f6
Create Date: 2026-11-26 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "b7e1c2d3f4a5"
down_revision: str | Sequence[str] | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "votings",
        sa.Column("voting_id", sa.Text(), nullable=False),
        sa.Column("session", sa.Text(), nullable=True),
        sa.Column("year", sa.Integer(), nullable=True),
        sa.Column("number", sa.Integer(), nullable=True),
        sa.Column("voted_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("item_title", sa.Text(), nullable=True),
        sa.Column("stage", sa.Text(), nullable=True),
        sa.Column("document_ref", sa.Text(), nullable=True),
        sa.Column("document_type", sa.Text(), nullable=True),
        sa.Column("cancelled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("result", postgresql.JSONB(), nullable=True),
        sa.Column("group_results", postgresql.JSONB(), nullable=True),
        sa.Column("government_opposition", postgresql.JSONB(), nullable=True),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("voting_id"),
    )
    op.create_index("ix_votings_year", "votings", ["year"])


def downgrade() -> None:
    op.drop_index("ix_votings_year", table_name="votings")
    op.drop_table("votings")
