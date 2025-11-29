"""add_keywords_to_topic

Revision ID: f166683ae919
Revises: 57fe51059efd
Create Date: 2025-11-28 23:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'f166683ae919'
down_revision: Union[str, None] = '57fe51059efd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add keywords JSONB column to topic table
    op.add_column('topic', sa.Column('keywords', postgresql.JSONB(), nullable=True))

    # Add GIN index for efficient keyword search
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_topic_keywords
        ON topic USING GIN (keywords)
    """)

    # Add column comment
    op.execute("""
        COMMENT ON COLUMN topic.keywords IS
        'Top keywords from BERTopic c-TF-IDF (JSONB array with keyword and score)'
    """)


def downgrade() -> None:
    # Drop index and column
    op.execute("DROP INDEX IF EXISTS idx_topic_keywords")
    op.drop_column('topic', 'keywords')
