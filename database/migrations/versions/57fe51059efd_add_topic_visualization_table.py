"""add_topic_visualization_table

Revision ID: 57fe51059efd
Revises: f8510f5a8af2
Create Date: 2025-11-24 09:59:57.273987

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '57fe51059efd'
down_revision: Union[str, None] = 'f8510f5a8af2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create topic_visualization table (single row for latest visualization)
    op.create_table(
        'topic_visualization',
        sa.Column('id', sa.Integer(), nullable=False, default=1),
        sa.Column('news_date', sa.Date(), nullable=False),
        sa.Column('image_data', sa.LargeBinary(), nullable=False),
        sa.Column('dpi', sa.Integer(), nullable=True, default=150),
        sa.Column('article_count', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.text('NOW()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint('id = 1', name='single_row_check')
    )


def downgrade() -> None:
    op.drop_table('topic_visualization')
