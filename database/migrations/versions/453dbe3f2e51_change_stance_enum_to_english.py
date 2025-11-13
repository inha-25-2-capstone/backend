"""change_stance_enum_to_english

Revision ID: 453dbe3f2e51
Revises: 9cb8fe3d195b
Create Date: 2025-11-12 18:29:36.563445

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '453dbe3f2e51'
down_revision: Union[str, None] = '9cb8fe3d195b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Change stance_type ENUM from Korean to English"""

    # Step 1: Drop the check constraint that references the ENUM
    op.execute("""
        ALTER TABLE stance_analysis
        DROP CONSTRAINT IF EXISTS chk_stance_consistency
    """)

    # Step 2: Convert columns to TEXT temporarily
    op.execute("ALTER TABLE topic ALTER COLUMN main_stance TYPE TEXT")
    op.execute("ALTER TABLE stance_analysis ALTER COLUMN stance_label TYPE TEXT")
    op.execute("ALTER TABLE recommended_article ALTER COLUMN recommendation_type TYPE TEXT")

    # Step 3: Update data from Korean to English
    op.execute("""
        UPDATE topic
        SET main_stance = CASE
            WHEN main_stance = '옹호' THEN 'support'
            WHEN main_stance = '중립' THEN 'neutral'
            WHEN main_stance = '비판' THEN 'oppose'
            ELSE main_stance
        END
    """)

    op.execute("""
        UPDATE stance_analysis
        SET stance_label = CASE
            WHEN stance_label = '옹호' THEN 'support'
            WHEN stance_label = '중립' THEN 'neutral'
            WHEN stance_label = '비판' THEN 'oppose'
            ELSE stance_label
        END
    """)

    op.execute("""
        UPDATE recommended_article
        SET recommendation_type = CASE
            WHEN recommendation_type = '옹호' THEN 'support'
            WHEN recommendation_type = '중립' THEN 'neutral'
            WHEN recommendation_type = '비판' THEN 'oppose'
            ELSE recommendation_type
        END
    """)

    # Step 4: Drop old ENUM type
    op.execute("DROP TYPE stance_type")

    # Step 5: Create new ENUM type with English values
    op.execute("""
        CREATE TYPE stance_type AS ENUM ('support', 'neutral', 'oppose')
    """)

    # Step 6: Convert columns back to the new ENUM type
    op.execute("ALTER TABLE topic ALTER COLUMN main_stance TYPE stance_type USING main_stance::stance_type")
    op.execute("ALTER TABLE stance_analysis ALTER COLUMN stance_label TYPE stance_type USING stance_label::stance_type")
    op.execute("ALTER TABLE recommended_article ALTER COLUMN recommendation_type TYPE stance_type USING recommendation_type::stance_type")

    # Step 7: Re-add the check constraint with English values
    op.execute("""
        ALTER TABLE stance_analysis
        ADD CONSTRAINT chk_stance_consistency CHECK (
            (stance_label = 'support' AND prob_positive >= prob_neutral AND prob_positive >= prob_negative) OR
            (stance_label = 'neutral' AND prob_neutral >= prob_positive AND prob_neutral >= prob_negative) OR
            (stance_label = 'oppose' AND prob_negative >= prob_positive AND prob_negative >= prob_neutral)
        )
    """)


def downgrade() -> None:
    """Revert stance_type ENUM from English to Korean"""

    # Step 1: Drop the check constraint
    op.execute("""
        ALTER TABLE stance_analysis
        DROP CONSTRAINT IF EXISTS chk_stance_consistency
    """)

    # Step 2: Convert columns to TEXT temporarily
    op.execute("ALTER TABLE topic ALTER COLUMN main_stance TYPE TEXT")
    op.execute("ALTER TABLE stance_analysis ALTER COLUMN stance_label TYPE TEXT")
    op.execute("ALTER TABLE recommended_article ALTER COLUMN recommendation_type TYPE TEXT")

    # Step 3: Update data from English to Korean
    op.execute("""
        UPDATE topic
        SET main_stance = CASE
            WHEN main_stance = 'support' THEN '옹호'
            WHEN main_stance = 'neutral' THEN '중립'
            WHEN main_stance = 'oppose' THEN '비판'
            ELSE main_stance
        END
    """)

    op.execute("""
        UPDATE stance_analysis
        SET stance_label = CASE
            WHEN stance_label = 'support' THEN '옹호'
            WHEN stance_label = 'neutral' THEN '중립'
            WHEN stance_label = 'oppose' THEN '비판'
            ELSE stance_label
        END
    """)

    op.execute("""
        UPDATE recommended_article
        SET recommendation_type = CASE
            WHEN recommendation_type = 'support' THEN '옹호'
            WHEN recommendation_type = 'neutral' THEN '중립'
            WHEN recommendation_type = 'oppose' THEN '비판'
            ELSE recommendation_type
        END
    """)

    # Step 4: Drop ENUM type
    op.execute("DROP TYPE stance_type")

    # Step 5: Create ENUM type with Korean values
    op.execute("""
        CREATE TYPE stance_type AS ENUM ('옹호', '중립', '비판')
    """)

    # Step 6: Convert columns back to the ENUM type
    op.execute("ALTER TABLE topic ALTER COLUMN main_stance TYPE stance_type USING main_stance::stance_type")
    op.execute("ALTER TABLE stance_analysis ALTER COLUMN stance_label TYPE stance_type USING stance_label::stance_type")
    op.execute("ALTER TABLE recommended_article ALTER COLUMN recommendation_type TYPE stance_type USING recommendation_type::stance_type")

    # Step 7: Re-add the check constraint with Korean values
    op.execute("""
        ALTER TABLE stance_analysis
        ADD CONSTRAINT chk_stance_consistency CHECK (
            (stance_label = '옹호' AND prob_positive >= prob_neutral AND prob_positive >= prob_negative) OR
            (stance_label = '중립' AND prob_neutral >= prob_positive AND prob_neutral >= prob_negative) OR
            (stance_label = '비판' AND prob_negative >= prob_positive AND prob_negative >= prob_neutral)
        )
    """)
