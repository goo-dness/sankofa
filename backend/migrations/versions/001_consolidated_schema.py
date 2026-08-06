"""Consolidated schema - all 7 tables

Revision ID: 001_consolidated
Revises: 
Create Date: 2026-07-18

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = '001_consolidated'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. relationship_types (referenced by entity_relations)
    op.create_table(
        'relationship_types',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('name', sa.String(), nullable=False, unique=True),
        sa.Column('label', sa.String(), nullable=False),
        sa.Column('domain', sa.String(), nullable=False),
        sa.Column('description', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_relationship_types_id', 'relationship_types', ['id'])

    # 2. entities (referenced by entity_relations, entity_sources, entity_names, entity_people)
    op.create_table(
        'entities',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('domain', sa.String(), nullable=True),
        sa.Column('entity_type', sa.String(), nullable=True),
        sa.Column('region', sa.String(), nullable=True),
        sa.Column('original_lang', sa.String(), nullable=True),
        sa.Column('expression', sa.String(), nullable=True),
        sa.Column('confidence', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('contributor', sa.String(), nullable=True),
        sa.Column('evidence_count', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_entities_id', 'entities', ['id'])
    op.create_index('ix_entities_name', 'entities', ['name'])

    # 3. entity_relations (the edge table)
    op.create_table(
        'entity_relations',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('from_entity_id', sa.Integer(), sa.ForeignKey('entities.id'), nullable=False),
        sa.Column('to_entity_id', sa.Integer(), sa.ForeignKey('entities.id'), nullable=False),
        sa.Column('relationship_id', sa.Integer(), sa.ForeignKey('relationship_types.id'), nullable=False),
        sa.Column('confidence', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('evidence_count', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('context', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_entity_relations_id', 'entity_relations', ['id'])

    # 4. entity_sources
    op.create_table(
        'entity_sources',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('entity_id', sa.Integer(), sa.ForeignKey('entities.id'), nullable=False),
        sa.Column('source_name', sa.String(), nullable=True),
        sa.Column('source_url', sa.String(), nullable=True),
        sa.Column('source_author', sa.String(), nullable=True),
        sa.Column('source_title', sa.String(), nullable=True),
        sa.Column('access_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_entity_sources_id', 'entity_sources', ['id'])

    # 5. relationship_sources
    op.create_table(
        'relationship_sources',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('relationship_id', sa.Integer(), sa.ForeignKey('entity_relations.id'), nullable=False),
        sa.Column('source_name', sa.String(), nullable=False),
        sa.Column('source_url', sa.String(), nullable=False),
        sa.Column('source_author', sa.String(), nullable=True),
        sa.Column('source_title', sa.String(), nullable=True),
        sa.Column('confidence', sa.Integer(), nullable=False),
        sa.Column('context', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # 6. entity_names
    op.create_table(
        'entity_names',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('entity_id', sa.Integer(), sa.ForeignKey('entities.id'), nullable=False),
        sa.Column('name', sa.String(), nullable=True),
        sa.Column('language', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_entity_names_id', 'entity_names', ['id'])

    # 7. entity_people
    op.create_table(
        'entity_people',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('entity_id', sa.Integer(), sa.ForeignKey('entities.id'), nullable=False),
        sa.Column('people_name', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_entity_people_id', 'entity_people', ['id'])


def downgrade() -> None:
    op.drop_table('entity_people')
    op.drop_table('entity_names')
    op.drop_table('relationship_sources')
    op.drop_table('entity_sources')
    op.drop_table('entity_relations')
    op.drop_table('entities')
    op.drop_table('relationship_types')
