"""add_relationship_id_index

Revision ID: 23bba8647084
Revises: 826063ca0268
Create Date: 2026-07-28 22:57:02.764427

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '23bba8647084'
down_revision: Union[str, Sequence[str], None] = '826063ca0268'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_index(
        'ix_entity_relations_relationship_id',
            'entity_relations', ['relationship_id'],
            unique=False
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        'ix_entity_relations_relationship_id',
        table_name='entity_relations'
    )
