"""add_unique_entity_name_domain

Revision ID: 826063ca0268
Revises: 57bcc7ad89bf
Create Date: 2026-07-28 21:25:43.036140

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '826063ca0268'
down_revision: Union[str, Sequence[str], None] = '57bcc7ad89bf'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_index(
        'uq_entities_name_domain',
        'entities',
        [sa.text('lower(trim(name))'), 'domain'],
        unique=True
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('uq_entities_name_domain', table_name='entities')
