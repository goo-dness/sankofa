"""add relationship_type to ingestion_coverage

Revision ID: ec1d6421e4e9
Revises: 23bba8647084
Create Date: 2026-07-31 20:27:48.504570

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ec1d6421e4e9'
down_revision: Union[str, Sequence[str], None] = '23bba8647084'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("TRUNCATE TABLE ingestion_coverage")
    op.drop_constraint('uq_disease_source', 'ingestion_coverage', type_='unique')
    op.add_column('ingestion_coverage', sa.Column('relationship_type', sa.String(), nullable=False))
    op.create_unique_constraint('uq_disease_source_reltype', 'ingestion_coverage', ['disease_name', 'source_name', 'relationship_type'])
    # ### end Alembic commands ###


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('uq_disease_source_reltype', 'ingestion_coverage', type_='unique')
    op.drop_column('ingestion_coverage', 'relationship_type')
    op.create_unique_constraint('uq_disease_source', 'ingestion_coverage', ['disease_name', 'source_name'])
    # ### end Alembic commands ###
