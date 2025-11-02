"""add_updated_at_to_article

Revision ID: 1cd4d0dee946
Revises: 84b2e5a1078e
Create Date: 2025-10-23 01:15:51.892355

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1cd4d0dee946'
down_revision: Union[str, None] = '84b2e5a1078e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add updated_at column to article table
    op.execute("""
        ALTER TABLE article
        ADD COLUMN updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
    """)

    # Initialize existing rows with created_at value
    op.execute("""
        UPDATE article
        SET updated_at = created_at
        WHERE updated_at IS NULL
    """)

    # Create trigger to auto-update updated_at
    op.execute("""
        CREATE OR REPLACE FUNCTION update_article_updated_at()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = NOW();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
    """)

    op.execute("""
        DROP TRIGGER IF EXISTS trg_update_article_updated_at ON article
    """)

    op.execute("""
        CREATE TRIGGER trg_update_article_updated_at
        BEFORE UPDATE ON article
        FOR EACH ROW
        EXECUTE FUNCTION update_article_updated_at()
    """)


def downgrade() -> None:
    # Drop trigger and function
    op.execute("DROP TRIGGER IF EXISTS trg_update_article_updated_at ON article")
    op.execute("DROP FUNCTION IF EXISTS update_article_updated_at()")

    # Drop column
    op.execute("ALTER TABLE article DROP COLUMN IF EXISTS updated_at")
