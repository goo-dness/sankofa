"""Add ingestion_coverage table for three-state epistemic awareness

Revision ID: 002_add_coverage
Revises: 001_consolidated
Create Date: 2026-07-18

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = '002_add_coverage'
down_revision = '001_consolidated'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'ingestion_coverage',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('domain', sa.String(), nullable=False),
        sa.Column('disease_name', sa.String(), nullable=False),
        sa.Column('source_name', sa.String(), nullable=False),
        sa.Column('last_ingested_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint('disease_name', 'source_name', name='uq_disease_source'),
    )
    op.create_index('ix_coverage_disease', 'ingestion_coverage', ['disease_name'])
    op.create_index('ix_coverage_domain', 'ingestion_coverage', ['domain'])


def downgrade() -> None:
    op.drop_table('ingestion_coverage')
