"""update_topic_rank_constraint_to_10

Revision ID: 84b2e5a1078e
Revises: 79873a2e1c49
Create Date: 2025-10-23 00:08:18.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '84b2e5a1078e'
down_revision: Union[str, None] = '79873a2e1c49'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop the old constraint
    op.drop_constraint('chk_topic_rank', 'topic', type_='check')

    # Add the new constraint allowing 1-10
    op.create_check_constraint(
        'chk_topic_rank',
        'topic',
        'topic_rank >= 1 AND topic_rank <= 10'
    )


def downgrade() -> None:
    # Drop the new constraint
    op.drop_constraint('chk_topic_rank', 'topic', type_='check')

    # Restore the old constraint allowing 1-7
    op.create_check_constraint(
        'chk_topic_rank',
        'topic',
        'topic_rank >= 1 AND topic_rank <= 7'
    )
