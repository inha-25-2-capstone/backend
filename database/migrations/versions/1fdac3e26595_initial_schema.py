"""initial_schema

Revision ID: 1fdac3e26595
Revises:
Create Date: 2025-10-18 00:49:15.690494

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1fdac3e26595'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create initial database schema with pgvector support"""

    # Enable pgvector extension
    op.execute('CREATE EXTENSION IF NOT EXISTS vector')

    # Create stance_type enum
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'stance_type') THEN
                CREATE TYPE stance_type AS ENUM ('옹호', '중립', '비판');
            END IF;
        END $$;
    """)

    # 1. Create press table
    op.execute("""
        CREATE TABLE IF NOT EXISTS press (
            press_id VARCHAR(10) PRIMARY KEY,
            press_name VARCHAR(100) NOT NULL UNIQUE,
            created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 2. Create article table
    op.execute("""
        CREATE TABLE IF NOT EXISTS article (
            article_id BIGSERIAL PRIMARY KEY,
            press_id VARCHAR(10) NOT NULL,
            news_date DATE NOT NULL,
            author VARCHAR(100),
            title VARCHAR(300) NOT NULL,
            content TEXT NOT NULL,
            summary TEXT,
            article_url VARCHAR(2083) NOT NULL UNIQUE,
            img_url VARCHAR(2083),
            published_at TIMESTAMPTZ NOT NULL,
            created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,

            CONSTRAINT fk_article_press FOREIGN KEY (press_id) REFERENCES press(press_id),
            CONSTRAINT chk_published_at CHECK (published_at <= NOW()),
            CONSTRAINT chk_author_not_empty CHECK (author IS NULL OR TRIM(author) != '')
        )
    """)

    # Create article indexes
    op.execute('CREATE INDEX IF NOT EXISTS idx_published_at ON article(published_at)')
    op.execute('CREATE INDEX IF NOT EXISTS idx_press_published ON article(press_id, published_at)')
    op.execute('CREATE INDEX IF NOT EXISTS idx_news_date ON article(news_date DESC)')

    # 3. Create topic table
    op.execute("""
        CREATE TABLE IF NOT EXISTS topic (
            topic_id BIGSERIAL PRIMARY KEY,
            topic_title VARCHAR(500) NOT NULL,
            main_article_id BIGINT NOT NULL,
            main_stance stance_type NOT NULL,
            main_stance_score DECIMAL(6, 5) NOT NULL,
            topic_date DATE NOT NULL,
            topic_rank SMALLINT NOT NULL,
            cluster_score DECIMAL(10, 5) NOT NULL,
            article_count INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,

            CONSTRAINT fk_topic_main_article FOREIGN KEY (main_article_id) REFERENCES article(article_id),
            CONSTRAINT chk_topic_rank CHECK (topic_rank BETWEEN 1 AND 7),
            CONSTRAINT chk_main_stance_score CHECK (main_stance_score BETWEEN -1 AND 1),
            CONSTRAINT uq_topic_date_rank UNIQUE (topic_date, topic_rank)
        )
    """)

    # Create topic indexes
    op.execute('CREATE INDEX IF NOT EXISTS idx_topic_date_rank ON topic(topic_date, topic_rank)')
    op.execute('CREATE INDEX IF NOT EXISTS idx_cluster_score ON topic(topic_date, cluster_score DESC)')

    # 4. Create topic_article_mapping table
    op.execute("""
        CREATE TABLE IF NOT EXISTS topic_article_mapping (
            topic_article_id BIGSERIAL PRIMARY KEY,
            topic_id BIGINT NOT NULL,
            article_id BIGINT NOT NULL,
            similarity_score DECIMAL(6, 5) NOT NULL,
            topic_date DATE NOT NULL,
            created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,

            CONSTRAINT fk_mapping_topic FOREIGN KEY (topic_id) REFERENCES topic(topic_id) ON DELETE CASCADE,
            CONSTRAINT fk_mapping_article FOREIGN KEY (article_id) REFERENCES article(article_id) ON DELETE CASCADE,
            CONSTRAINT chk_similarity_score CHECK (similarity_score BETWEEN 0 AND 1),
            CONSTRAINT uq_topic_article UNIQUE (topic_id, article_id),
            CONSTRAINT uq_article_topic_date UNIQUE (article_id, topic_date)
        )
    """)

    # Create topic_article_mapping indexes
    op.execute('CREATE INDEX IF NOT EXISTS idx_similarity ON topic_article_mapping(topic_id, similarity_score DESC)')
    op.execute('CREATE INDEX IF NOT EXISTS idx_article_date ON topic_article_mapping(article_id, topic_date)')
    op.execute('CREATE INDEX IF NOT EXISTS idx_article_topic ON topic_article_mapping(article_id)')

    # 5. Create stance_analysis table
    op.execute("""
        CREATE TABLE IF NOT EXISTS stance_analysis (
            stance_id BIGSERIAL PRIMARY KEY,
            article_id BIGINT NOT NULL UNIQUE,
            stance_label stance_type NOT NULL,
            prob_positive DECIMAL(6, 5) NOT NULL,
            prob_neutral DECIMAL(6, 5) NOT NULL,
            prob_negative DECIMAL(6, 5) NOT NULL,
            stance_score DECIMAL(6, 5) NOT NULL,
            analyzed_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,

            CONSTRAINT fk_stance_article FOREIGN KEY (article_id) REFERENCES article(article_id),
            CONSTRAINT chk_prob_positive CHECK (prob_positive BETWEEN 0 AND 1),
            CONSTRAINT chk_prob_neutral CHECK (prob_neutral BETWEEN 0 AND 1),
            CONSTRAINT chk_prob_negative CHECK (prob_negative BETWEEN 0 AND 1),
            CONSTRAINT chk_stance_score CHECK (stance_score BETWEEN -1 AND 1),
            CONSTRAINT chk_prob_sum CHECK (ABS(prob_positive + prob_neutral + prob_negative - 1.0) <= 0.001),
            CONSTRAINT chk_stance_consistency CHECK (
                (stance_label = '옹호' AND prob_positive >= prob_neutral AND prob_positive >= prob_negative) OR
                (stance_label = '중립' AND prob_neutral >= prob_positive AND prob_neutral >= prob_negative) OR
                (stance_label = '비판' AND prob_negative >= prob_positive AND prob_negative >= prob_neutral)
            )
        )
    """)

    # Create stance_analysis indexes
    op.execute('CREATE INDEX IF NOT EXISTS idx_stance_score ON stance_analysis(stance_label, stance_score)')
    op.execute('CREATE INDEX IF NOT EXISTS idx_article_stance ON stance_analysis(article_id, stance_label)')

    # 6. Create recommended_article table
    op.execute("""
        CREATE TABLE IF NOT EXISTS recommended_article (
            recommended_id BIGSERIAL PRIMARY KEY,
            topic_id BIGINT NOT NULL,
            article_id BIGINT NOT NULL,
            press_id VARCHAR(10) NOT NULL,
            press_name VARCHAR(100) NOT NULL,
            title VARCHAR(300) NOT NULL,
            author VARCHAR(100),
            img_url VARCHAR(2083),
            article_url VARCHAR(2083) NOT NULL,
            recommendation_type stance_type NOT NULL,
            recommendation_rank SMALLINT NOT NULL,
            stance_score DECIMAL(6, 5) NOT NULL,
            published_at TIMESTAMPTZ NOT NULL,
            created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,

            CONSTRAINT fk_recommended_topic FOREIGN KEY (topic_id) REFERENCES topic(topic_id) ON DELETE CASCADE,
            CONSTRAINT fk_recommended_article FOREIGN KEY (article_id) REFERENCES article(article_id) ON DELETE CASCADE,
            CONSTRAINT fk_recommended_press FOREIGN KEY (press_id) REFERENCES press(press_id),
            CONSTRAINT chk_recommendation_rank CHECK (recommendation_rank BETWEEN 1 AND 3),
            CONSTRAINT chk_recommended_stance_score CHECK (stance_score BETWEEN -1 AND 1),
            CONSTRAINT uq_topic_type_rank UNIQUE (topic_id, recommendation_type, recommendation_rank),
            CONSTRAINT uq_recommended_topic_article UNIQUE (topic_id, article_id)
        )
    """)

    # Create recommended_article indexes
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_topic_type_rank ON recommended_article(
            topic_id,
            recommendation_type,
            recommendation_rank
        )
    """)

    # 7. Create triggers for article_count auto-update
    op.execute("""
        CREATE OR REPLACE FUNCTION update_article_count_on_insert()
        RETURNS TRIGGER AS $$
        BEGIN
            UPDATE topic
            SET article_count = article_count + 1
            WHERE topic_id = NEW.topic_id;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
    """)

    op.execute("""
        CREATE OR REPLACE FUNCTION update_article_count_on_delete()
        RETURNS TRIGGER AS $$
        BEGIN
            UPDATE topic
            SET article_count = article_count - 1
            WHERE topic_id = OLD.topic_id;
            RETURN OLD;
        END;
        $$ LANGUAGE plpgsql
    """)

    op.execute("""
        DROP TRIGGER IF EXISTS trg_update_article_count_insert ON topic_article_mapping
    """)
    op.execute("""
        CREATE TRIGGER trg_update_article_count_insert
        AFTER INSERT ON topic_article_mapping
        FOR EACH ROW
        EXECUTE FUNCTION update_article_count_on_insert()
    """)

    op.execute("""
        DROP TRIGGER IF EXISTS trg_update_article_count_delete ON topic_article_mapping
    """)
    op.execute("""
        CREATE TRIGGER trg_update_article_count_delete
        AFTER DELETE ON topic_article_mapping
        FOR EACH ROW
        EXECUTE FUNCTION update_article_count_on_delete()
    """)


def downgrade() -> None:
    """Drop all tables and related objects"""

    # Drop triggers
    op.execute('DROP TRIGGER IF EXISTS trg_update_article_count_delete ON topic_article_mapping')
    op.execute('DROP TRIGGER IF EXISTS trg_update_article_count_insert ON topic_article_mapping')

    # Drop trigger functions
    op.execute('DROP FUNCTION IF EXISTS update_article_count_on_delete()')
    op.execute('DROP FUNCTION IF EXISTS update_article_count_on_insert()')

    # Drop tables (in reverse order due to foreign keys)
    op.execute('DROP TABLE IF EXISTS recommended_article CASCADE')
    op.execute('DROP TABLE IF EXISTS stance_analysis CASCADE')
    op.execute('DROP TABLE IF EXISTS topic_article_mapping CASCADE')
    op.execute('DROP TABLE IF EXISTS topic CASCADE')
    op.execute('DROP TABLE IF EXISTS article CASCADE')
    op.execute('DROP TABLE IF EXISTS press CASCADE')

    # Drop enum type
    op.execute('DROP TYPE IF EXISTS stance_type CASCADE')

    # Note: We don't drop the vector extension as it might be used by other databases
