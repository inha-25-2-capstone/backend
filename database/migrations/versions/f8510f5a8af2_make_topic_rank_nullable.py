"""make_topic_rank_nullable

Revision ID: f8510f5a8af2
Revises: 767f2eee2ba6
Create Date: 2025-11-19 16:10:43.388260

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f8510f5a8af2'
down_revision: Union[str, None] = '767f2eee2ba6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Make topic_rank nullable (not all topics get ranked, only top 10)
    op.alter_column('topic', 'topic_rank',
                    existing_type=sa.SMALLINT(),
                    nullable=True)


def downgrade() -> None:
    # Revert topic_rank to NOT NULL
    op.alter_column('topic', 'topic_rank',
                    existing_type=sa.SMALLINT(),
                    nullable=False)
