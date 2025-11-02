"""update_rank_score_precision

Revision ID: 79873a2e1c49
Revises: 6659f7177381
Create Date: 2025-10-22 23:17:00.468811

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '79873a2e1c49'
down_revision: Union[str, None] = '6659f7177381'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Change rank_score from NUMERIC(5,3) to NUMERIC(10,3)
    op.alter_column('topic', 'rank_score',
                    type_=sa.NUMERIC(precision=10, scale=3),
                    existing_type=sa.NUMERIC(precision=5, scale=3),
                    existing_nullable=True)


def downgrade() -> None:
    # Revert rank_score back to NUMERIC(5,3)
    op.alter_column('topic', 'rank_score',
                    type_=sa.NUMERIC(precision=5, scale=3),
                    existing_type=sa.NUMERIC(precision=10, scale=3),
                    existing_nullable=True)
