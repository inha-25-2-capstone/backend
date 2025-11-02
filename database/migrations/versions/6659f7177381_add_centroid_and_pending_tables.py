"""add_centroid_and_pending_tables

Revision ID: 6659f7177381
Revises: 50f79b54aace
Create Date: 2025-10-20 15:58:09.880211

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6659f7177381'
down_revision: Union[str, None] = '50f79b54aace'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add centroid_embedding column to topic table
    op.execute("ALTER TABLE topic ADD COLUMN IF NOT EXISTS centroid_embedding vector(768)")

    # Add metadata columns to topic table
    op.add_column('topic', sa.Column('rank_score', sa.DECIMAL(5, 3), nullable=True))
    op.add_column('topic', sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False))
    op.add_column('topic', sa.Column('last_updated', sa.TIMESTAMP(), server_default=sa.func.now(), nullable=False))

    # Create pending_articles table
    op.create_table(
        'pending_articles',
        sa.Column('article_id', sa.Integer(), primary_key=True),
        sa.Column('added_at', sa.TIMESTAMP(), server_default=sa.func.now(), nullable=False),
        sa.Column('reason', sa.VARCHAR(50), nullable=True),
        sa.Column('max_similarity', sa.DECIMAL(5, 3), nullable=True),
        sa.ForeignKeyConstraint(['article_id'], ['article.article_id'], ondelete='CASCADE')
    )

    # Create index on added_at for efficient time-based queries
    op.create_index('idx_pending_articles_added_at', 'pending_articles', ['added_at'])


def downgrade() -> None:
    # Drop pending_articles table
    op.drop_index('idx_pending_articles_added_at', 'pending_articles')
    op.drop_table('pending_articles')

    # Remove columns from topic table
    op.drop_column('topic', 'last_updated')
    op.drop_column('topic', 'is_active')
    op.drop_column('topic', 'rank_score')
    op.execute("ALTER TABLE topic DROP COLUMN IF EXISTS centroid_embedding")
