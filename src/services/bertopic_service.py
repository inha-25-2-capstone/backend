"""
BERTopic Helper Functions (Data Fetching Only)

Main BERTopic clustering logic has been moved to HF Spaces AI Service.
This module only contains helper functions for fetching article data from database.
"""
import numpy as np
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime

from src.models.database import get_db_connection
from src.utils.logger import setup_logger

logger = setup_logger()


def fetch_articles_with_embeddings(
    news_date: Optional[datetime.date] = None,
    limit: int = 200
) -> Tuple[List[Dict], Optional[np.ndarray], List[str]]:
    """
    Fetch articles with embeddings from database.

    Args:
        news_date: Optional date to filter by news_date
        limit: Maximum number of articles

    Returns:
        Tuple of (articles, embeddings, doc_texts):
        - articles: List of dicts with article_id, title, summary
        - embeddings: numpy array of shape (n_articles, 768)
        - doc_texts: List of "title. summary" strings
    """
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            if news_date:
                query = """
                    SELECT article_id, title, summary, embedding
                    FROM article
                    WHERE summary IS NOT NULL
                      AND embedding IS NOT NULL
                      AND news_date = %s
                    ORDER BY created_at DESC
                    LIMIT %s
                """
                cursor.execute(query, (news_date, limit))
            else:
                query = """
                    SELECT article_id, title, summary, embedding
                    FROM article
                    WHERE summary IS NOT NULL
                      AND embedding IS NOT NULL
                    ORDER BY created_at DESC
                    LIMIT %s
                """
                cursor.execute(query, (limit,))

            rows = cursor.fetchall()

            if not rows:
                logger.warning("No articles with embeddings found")
                return [], None, []

            articles = []
            embeddings_list = []
            doc_texts = []

            for row in rows:
                articles.append({
                    'article_id': row[0],
                    'title': row[1],
                    'summary': row[2]
                })

                # Embedding from pgvector - convert from string if needed
                embedding = row[3]
                if isinstance(embedding, str):
                    # Parse string representation: "[0.1, 0.2, ...]"
                    import json
                    embedding = json.loads(embedding)
                embeddings_list.append(embedding)

                # Document text for BERTopic (title + summary)
                doc_texts.append(f"{row[1]}. {row[2]}")

            # Convert to numpy array
            embeddings_array = np.array(embeddings_list, dtype=np.float32)

            logger.info(f"Fetched {len(articles)} articles with embeddings")

            return articles, embeddings_array, doc_texts


def get_article_news_date(article_id: int) -> Optional[datetime.date]:
    """Get news_date for an article."""
    from src.models.database import ArticleRepository
    article = ArticleRepository.get_by_id(article_id)
    return article['news_date'] if article else None
