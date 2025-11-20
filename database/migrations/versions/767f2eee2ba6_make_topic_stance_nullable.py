"""make_topic_stance_nullable

Revision ID: 767f2eee2ba6
Revises: 453dbe3f2e51
Create Date: 2025-11-19 11:21:33.953232

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '767f2eee2ba6'
down_revision: Union[str, None] = '453dbe3f2e51'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Make main_stance and main_stance_score nullable in topic table
    op.alter_column('topic', 'main_stance',
                    existing_type=sa.Enum('support', 'neutral', 'oppose', name='stance_type'),
                    nullable=True)
    op.alter_column('topic', 'main_stance_score',
                    existing_type=sa.NUMERIC(precision=6, scale=5),
                    nullable=True)


def downgrade() -> None:
    # Revert: make main_stance and main_stance_score NOT NULL
    op.alter_column('topic', 'main_stance',
                    existing_type=sa.Enum('support', 'neutral', 'oppose', name='stance_type'),
                    nullable=False)
    op.alter_column('topic', 'main_stance_score',
                    existing_type=sa.NUMERIC(precision=6, scale=5),
                    nullable=False)
