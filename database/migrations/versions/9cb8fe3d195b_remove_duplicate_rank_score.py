"""remove_duplicate_rank_score

Revision ID: 9cb8fe3d195b
Revises: 1cd4d0dee946
Create Date: 2025-10-23 01:17:06.212266

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9cb8fe3d195b'
down_revision: Union[str, None] = '1cd4d0dee946'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Remove duplicate rank_score column (cluster_score already exists)
    op.drop_column('topic', 'rank_score')


def downgrade() -> None:
    # Restore rank_score column if needed
    op.add_column('topic', sa.Column('rank_score', sa.DECIMAL(10, 3), nullable=True))
