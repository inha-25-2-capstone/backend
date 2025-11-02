"""add_embedding_column_to_article

Revision ID: 50f79b54aace
Revises: 1fdac3e26595
Create Date: 2025-10-20 09:58:45.894015

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '50f79b54aace'
down_revision: Union[str, None] = '1fdac3e26595'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add embedding column (768-dimensional vector for ko-sroberta-multitask)
    op.execute("""
        ALTER TABLE article
        ADD COLUMN embedding vector(768);
    """)

    # Create pgvector index for fast similarity search (cosine distance)
    op.execute("""
        CREATE INDEX idx_article_embedding_cosine
        ON article
        USING ivfflat (embedding vector_cosine_ops)
        WITH (lists = 100);
    """)

    # Add comment for documentation
    op.execute("""
        COMMENT ON COLUMN article.embedding IS
        '768-dimensional embedding vector from ko-sroberta-multitask model (normalized for cosine similarity)';
    """)


def downgrade() -> None:
    # Drop index first
    op.execute("DROP INDEX IF EXISTS idx_article_embedding_cosine;")

    # Drop column
    op.execute("ALTER TABLE article DROP COLUMN IF EXISTS embedding;")
