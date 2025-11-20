"""
Database models and connection management.
"""
import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2.pool import SimpleConnectionPool
from contextlib import contextmanager
from typing import Optional, Dict, List, Any
import logging
from datetime import datetime, timezone, timedelta

from src.config import DATABASE_URL

logger = logging.getLogger(__name__)

# Connection pool for efficient database connections
_connection_pool: Optional[SimpleConnectionPool] = None


def init_connection_pool(minconn: int = 1, maxconn: int = 10):
    """Initialize the database connection pool with keepalive settings."""
    global _connection_pool
    if _connection_pool is None:
        try:
            # Parse DATABASE_URL and add keepalive parameters
            import urllib.parse
            parsed = urllib.parse.urlparse(DATABASE_URL)

            # Build connection string with keepalive
            conn_params = {
                'keepalives': 1,
                'keepalives_idle': 30,
                'keepalives_interval': 10,
                'keepalives_count': 5,
                'connect_timeout': 10
            }

            _connection_pool = SimpleConnectionPool(
                minconn,
                maxconn,
                DATABASE_URL,
                **conn_params
            )
            logger.info(f"Database connection pool initialized (min={minconn}, max={maxconn}, keepalive enabled)")
        except Exception as e:
            logger.error(f"Failed to initialize connection pool: {e}")
            raise


def close_connection_pool():
    """Close all connections in the pool."""
    global _connection_pool
    if _connection_pool is not None:
        _connection_pool.closeall()
        _connection_pool = None
        logger.info("Database connection pool closed")


@contextmanager
def get_db_connection():
    """
    Context manager for database connections with retry logic.

    Usage:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM table")
    """
    global _connection_pool

    if _connection_pool is None:
        init_connection_pool()

    max_retries = 3
    retry_delay = 0.5  # Start with 500ms

    for attempt in range(max_retries):
        conn = None
        try:
            conn = _connection_pool.getconn()
            # Test connection with a simple query
            with conn.cursor() as test_cur:
                test_cur.execute("SELECT 1")

            yield conn
            conn.commit()
            break  # Success, exit retry loop

        except (psycopg2.OperationalError, psycopg2.InterfaceError) as e:
            # Connection-related errors - retry
            if conn:
                try:
                    conn.rollback()
                except Exception:
                    pass  # Connection already closed
                try:
                    _connection_pool.putconn(conn, close=True)  # Force close bad connection
                except Exception:
                    pass
                conn = None

            if attempt < max_retries - 1:
                import time
                time.sleep(retry_delay)
                retry_delay *= 2  # Exponential backoff
                logger.warning(f"DB connection error (attempt {attempt + 1}/{max_retries}): {e}. Retrying...")
            else:
                logger.error(f"DB connection failed after {max_retries} attempts: {e}")
                raise

        except Exception as e:
            # Other errors - don't retry
            if conn:
                try:
                    conn.rollback()
                except Exception:
                    pass
            logger.error(f"Database error: {e}")
            raise

        finally:
            if conn:
                _connection_pool.putconn(conn)


@contextmanager
def get_db_cursor(cursor_factory=RealDictCursor):
    """
    Context manager for database cursor.

    Usage:
        with get_db_cursor() as cur:
            cur.execute("SELECT * FROM table")
            results = cur.fetchall()
    """
    with get_db_connection() as conn:
        cursor = conn.cursor(cursor_factory=cursor_factory)
        try:
            yield cursor
        finally:
            cursor.close()


def calculate_news_date(published_at: datetime) -> datetime:
    """
    Calculate news_date based on KST 5:00 AM cutoff.

    Articles published before 5:00 AM belong to the previous day's news cycle.

    Args:
        published_at: Article publication datetime (should be in KST)

    Returns:
        news_date: Date for the news cycle (date only, no time)
    """
    # KST timezone (UTC+9)
    kst = timezone(timedelta(hours=9))

    # Ensure datetime is timezone-aware
    if published_at.tzinfo is None:
        published_at = published_at.replace(tzinfo=kst)

    # Convert to KST if not already
    kst_time = published_at.astimezone(kst)

    # If before 5:00 AM, belongs to previous day
    if kst_time.hour < 5:
        news_date = (kst_time - timedelta(days=1)).date()
    else:
        news_date = kst_time.date()

    return datetime.combine(news_date, datetime.min.time())


class PressRepository:
    """Repository for press (news organizations) operations."""

    @staticmethod
    def get_or_create(press_id: str, press_name: str) -> str:
        """
        Get or create press by ID and name.

        Args:
            press_id: Naver press ID code (e.g., "001")
            press_name: Name of the press organization

        Returns:
            press_id: ID of the press organization
        """
        with get_db_cursor() as cur:
            # Try to insert, if exists do nothing
            cur.execute(
                """
                INSERT INTO press (press_id, press_name)
                VALUES (%s, %s)
                ON CONFLICT (press_id) DO NOTHING
                """,
                (press_id, press_name)
            )

            if cur.rowcount > 0:
                logger.info(f"Created new press: {press_name} (ID: {press_id})")

            return press_id


class ArticleRepository:
    """Repository for article operations."""

    @staticmethod
    def exists_by_url(article_url: str) -> bool:
        """
        Check if an article with the given URL already exists.

        Args:
            article_url: Article URL

        Returns:
            True if exists, False otherwise
        """
        with get_db_cursor() as cur:
            cur.execute(
                "SELECT EXISTS(SELECT 1 FROM article WHERE article_url = %s)",
                (article_url,)
            )
            result = cur.fetchone()
            return result['exists'] if result else False

    @staticmethod
    def create(
        press_id: str,
        title: str,
        content: str,
        article_url: str,
        published_at: datetime,
        img_url: Optional[str] = None,
        author: Optional[str] = None
    ) -> int:
        """
        Create a new article.

        Args:
            press_id: ID of the press organization (Naver press code)
            title: Article title
            content: Article content
            article_url: Article URL
            published_at: Publication datetime (will be converted to UTC)
            img_url: Optional thumbnail image URL
            author: Optional article author

        Returns:
            article_id: ID of the created article
        """
        # Convert published_at to UTC for database storage
        if published_at.tzinfo is not None:
            published_at_utc = published_at.astimezone(timezone.utc)
        else:
            # If naive datetime, assume it's already UTC
            published_at_utc = published_at.replace(tzinfo=timezone.utc)

        news_date = calculate_news_date(published_at)

        with get_db_cursor() as cur:
            cur.execute(
                """
                INSERT INTO article (
                    press_id, title, content, article_url, published_at,
                    news_date, img_url, author, created_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
                RETURNING article_id
                """,
                (press_id, title, content, article_url, published_at_utc, news_date, img_url, author)
            )
            result = cur.fetchone()
            article_id = result['article_id']
            logger.debug(f"Created article: {title[:50]}... (ID: {article_id})")
            return article_id

    @staticmethod
    def get_by_id(article_id: int) -> Optional[Dict[str, Any]]:
        """Get article by ID."""
        with get_db_cursor() as cur:
            cur.execute(
                """
                SELECT a.*, p.press_name
                FROM article a
                JOIN press p ON a.press_id = p.press_id
                WHERE a.article_id = %s
                """,
                (article_id,)
            )
            return cur.fetchone()

    @staticmethod
    def get_by_date(news_date: datetime) -> List[Dict[str, Any]]:
        """Get all articles for a specific news date."""
        with get_db_cursor() as cur:
            cur.execute(
                """
                SELECT a.*, p.press_name
                FROM article a
                JOIN press p ON a.press_id = p.press_id
                WHERE a.news_date = %s
                ORDER BY a.published_at DESC
                """,
                (news_date,)
            )
            return cur.fetchall()

    @staticmethod
    def get_without_summary(limit: int = 100) -> List[Dict[str, Any]]:
        """Get articles that don't have summaries yet."""
        with get_db_cursor() as cur:
            cur.execute(
                """
                SELECT article_id, title, content, press_id
                FROM article
                WHERE summary IS NULL OR summary = ''
                ORDER BY published_at DESC
                LIMIT %s
                """,
                (limit,)
            )
            return cur.fetchall()

    @staticmethod
    def update_summary(article_id: int, summary: str):
        """Update article summary."""
        with get_db_cursor() as cur:
            cur.execute(
                """
                UPDATE article
                SET summary = %s, updated_at = NOW()
                WHERE article_id = %s
                """,
                (summary, article_id)
            )
            logger.debug(f"Updated summary for article {article_id}")

    @staticmethod
    def update_summary_and_embedding(
        article_id: int,
        summary: Optional[str] = None,
        embedding: Optional[str] = None
    ):
        """
        Update article summary and/or embedding.

        Args:
            article_id: Article ID
            summary: Summary text (optional)
            embedding: Embedding vector as string '[0.1,0.2,...]' (optional)
        """
        updates = []
        params = []

        if summary is not None:
            updates.append("summary = %s")
            params.append(summary)

        if embedding is not None:
            updates.append("embedding = %s::vector")
            params.append(embedding)

        if not updates:
            logger.warning(f"No updates provided for article {article_id}")
            return

        params.append(article_id)

        query = f"""
            UPDATE article
            SET {', '.join(updates)}
            WHERE article_id = %s
        """

        with get_db_cursor() as cur:
            cur.execute(query, params)
            logger.debug(
                f"Updated article {article_id} "
                f"(summary={'yes' if summary else 'no'}, "
                f"embedding={'yes' if embedding else 'no'})"
            )


# Initialize connection pool when module is imported
try:
    init_connection_pool()
except Exception as e:
    logger.warning(f"Could not initialize connection pool on import: {e}")
