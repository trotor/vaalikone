"""add indexes, vote subject_title, person_id, elections and candidates

Revision ID: 2914d0e98982
Revises: 9eb78cc50367
Create Date: 2026-11-25 05:34:37.316068

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '2914d0e98982'
down_revision: str | Sequence[str] | None = '9eb78cc50367'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    # --- new tables: elections + candidates ---
    op.create_table(
        'elections',
        sa.Column('year', sa.Integer(), nullable=False),
        sa.Column(
            'election_type',
            sa.Enum('EDUSKUNTAVAALIT', 'KUNTAVAALIT', 'EUROPARLAMENTTIVAALIT', 'PRESIDENTINVAALI', name='electiontype', native_enum=False),
            nullable=False,
        ),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('source_url', sa.Text(), nullable=True),
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('year', 'election_type', name='uq_elections_year_type'),
    )
    op.create_table(
        'candidates',
        sa.Column('election_id', sa.UUID(), nullable=False),
        sa.Column('party_id', sa.UUID(), nullable=True),
        sa.Column('candidate_number', sa.Text(), nullable=True),
        sa.Column('first_name', sa.Text(), nullable=False),
        sa.Column('last_name', sa.Text(), nullable=False),
        sa.Column('constituency', sa.Text(), nullable=True),
        sa.Column('votes', sa.Integer(), nullable=True),
        sa.Column('vote_share', sa.Float(), nullable=True),
        sa.Column('comparison_number', sa.Float(), nullable=True),
        sa.Column('elected', sa.Boolean(), nullable=False),
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.ForeignKeyConstraint(['election_id'], ['elections.id']),
        sa.ForeignKeyConstraint(['party_id'], ['parties.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_candidates_election_id', 'candidates', ['election_id'])
    op.create_index('ix_candidates_party_id', 'candidates', ['party_id'])
    op.create_index(
        'uq_candidates_election_number', 'candidates',
        ['election_id', 'candidate_number'], unique=True,
        postgresql_where=sa.text('candidate_number IS NOT NULL'),
    )

    # --- representatives: stable eduskunta person_id ---
    op.add_column('representatives', sa.Column('person_id', sa.Text(), nullable=True))
    # Backfill from social_media JSON (eduskunta_person_id)
    op.execute(
        "UPDATE representatives SET person_id = social_media->>'eduskunta_person_id' "
        "WHERE person_id IS NULL AND social_media ? 'eduskunta_person_id'"
    )
    # Null out duplicate person_ids (keep the first row) so the unique index can be created
    op.execute(
        "UPDATE representatives a SET person_id = NULL FROM representatives b "
        "WHERE a.person_id = b.person_id AND a.person_id IS NOT NULL AND a.id > b.id"
    )
    op.create_unique_constraint('uq_representatives_person_id', 'representatives', ['person_id'])
    op.create_index('ix_representatives_party_id', 'representatives', ['party_id'])

    # --- votes: subject title + dedup + indexes ---
    op.add_column('votes', sa.Column('subject_title', sa.Text(), nullable=True))
    # Remove duplicate votes (same representative + same äänestys), keep the first
    op.execute(
        "DELETE FROM votes a USING votes b "
        "WHERE a.id > b.id AND a.representative_id = b.representative_id "
        "AND a.subject IS NOT NULL AND a.subject = b.subject"
    )
    op.create_index('ix_votes_representative_id', 'votes', ['representative_id'])
    op.create_index('ix_votes_session', 'votes', ['session'])
    op.create_index('ix_votes_subject', 'votes', ['subject'])
    op.create_index(
        'uq_votes_representative_subject', 'votes',
        ['representative_id', 'subject'], unique=True,
        postgresql_where=sa.text('subject IS NOT NULL'),
    )

    # --- documents / embeddings indexes ---
    op.create_index('ix_documents_party_id', 'documents', ['party_id'])
    op.create_index('ix_documents_content_type', 'documents', ['content_type'])
    op.create_index('ix_documents_source_id', 'documents', ['source_id'])
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_documents_content_trgm ON documents "
        "USING gin (content_text gin_trgm_ops)"
    )
    op.create_index('ix_embeddings_document_id', 'embeddings', ['document_id'])
    op.create_index('ix_embeddings_model_name', 'embeddings', ['model_name'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_embeddings_model_name', table_name='embeddings')
    op.drop_index('ix_embeddings_document_id', table_name='embeddings')
    op.execute("DROP INDEX IF EXISTS ix_documents_content_trgm")
    op.drop_index('ix_documents_source_id', table_name='documents')
    op.drop_index('ix_documents_content_type', table_name='documents')
    op.drop_index('ix_documents_party_id', table_name='documents')
    op.drop_index('uq_votes_representative_subject', table_name='votes')
    op.drop_index('ix_votes_subject', table_name='votes')
    op.drop_index('ix_votes_session', table_name='votes')
    op.drop_index('ix_votes_representative_id', table_name='votes')
    op.drop_column('votes', 'subject_title')
    op.drop_index('ix_representatives_party_id', table_name='representatives')
    op.drop_constraint('uq_representatives_person_id', 'representatives', type_='unique')
    op.drop_column('representatives', 'person_id')
    op.drop_index('ix_candidates_party_id', table_name='candidates')
    op.drop_index('ix_candidates_election_id', table_name='candidates')
    op.drop_index('uq_candidates_election_number', table_name='candidates')
    op.drop_table('candidates')
    op.drop_table('elections')
