"""
Incremental Article Assignment Service
Assigns newly collected articles to existing topics in real-time
"""
import numpy as np
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta
import logging
import os

from src.utils.embeddings import parse_embedding_string, calculate_cosine_similarity, normalize_vector

logger = logging.getLogger(__name__)


class IncrementalAssigner:
    """
    Assigns new articles to existing topics based on embedding similarity
    """

    def __init__(self, conn, similarity_threshold: float = None, centroid_update_weight: float = None):
        """
        Initialize incremental assigner

        Args:
            conn: Database connection object
            similarity_threshold: Minimum cosine similarity to assign to topic (default: from env or 0.5)
            centroid_update_weight: Weight for centroid update (default: from env or 0.1)
        """
        self.conn = conn
        self.similarity_threshold = similarity_threshold or float(
            os.environ.get('INCREMENTAL_SIMILARITY_THRESHOLD', '0.5')
        )
        self.centroid_update_weight = centroid_update_weight or float(
            os.environ.get('INCREMENTAL_CENTROID_UPDATE_WEIGHT', '0.1')
        )

    def get_new_articles(
        self,
        since_minutes: int = 30
    ) -> List[Dict]:
        """
        Fetch articles collected in the last N minutes with embeddings

        Args:
            since_minutes: Look back window in minutes

        Returns:
            List of article dicts with id, embedding, title, summary
        """
        cutoff_time = datetime.now() - timedelta(minutes=since_minutes)

        with self.conn.cursor() as cur:
            # Get articles that have embeddings but are not assigned to any topic yet
            cur.execute(
                """
                SELECT
                    a.article_id,
                    a.title,
                    a.summary,
                    a.embedding::text as embedding_text,
                    a.published_at
                FROM article a
                LEFT JOIN topic_article_mapping tam ON a.article_id = tam.article_id
                WHERE a.embedding IS NOT NULL
                  AND a.published_at >= %s
                  AND tam.article_id IS NULL  -- Not assigned to any topic yet
                ORDER BY a.published_at DESC
                """,
                (cutoff_time,)
            )
            results = cur.fetchall()

        articles = []
        for row in results:
            # Parse embedding using utility function
            embedding = parse_embedding_string(row['embedding_text'])

            articles.append({
                'article_id': row['article_id'],
                'title': row['title'],
                'summary': row['summary'],
                'embedding': embedding,
                'published_at': row['published_at']
            })

        logger.info(f"Found {len(articles)} new articles to assign")
        return articles

    def get_active_topics(self, news_date: datetime) -> List[Dict]:
        """
        Fetch active topics for the given date with their centroids

        Args:
            news_date: Date to fetch topics for

        Returns:
            List of topic dicts with id, title, centroid_embedding
        """
        with self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    topic_id,
                    topic_title,
                    centroid_embedding::text as centroid_text,
                    article_count,
                    topic_rank
                FROM topic
                WHERE topic_date = %s
                  AND is_active = TRUE
                  AND centroid_embedding IS NOT NULL
                ORDER BY topic_rank
                """,
                (news_date,)
            )
            results = cur.fetchall()

        topics = []
        for row in results:
            # Parse centroid from text format
            centroid_str = row['centroid_text'].strip('[]')
            centroid = np.array([float(x) for x in centroid_str.split(',')])

            topics.append({
                'topic_id': row['topic_id'],
                'topic_title': row['topic_title'],
                'centroid_embedding': centroid,
                'article_count': row['article_count'],
                'topic_rank': row['topic_rank']
            })

        logger.info(f"Found {len(topics)} active topics for {news_date}")
        return topics


    def find_best_topic(
        self,
        article_embedding: np.ndarray,
        active_topics: List[Dict]
    ) -> Tuple[Optional[int], float]:
        """
        Find the best matching topic for an article

        Args:
            article_embedding: Article's embedding vector
            active_topics: List of active topics with centroids

        Returns:
            Tuple of (topic_id, similarity_score) or (None, max_similarity)
        """
        if not active_topics:
            return None, 0.0

        best_topic_id = None
        best_similarity = 0.0

        for topic in active_topics:
            similarity = calculate_cosine_similarity(
                article_embedding,
                topic['centroid_embedding']
            )

            if similarity > best_similarity:
                best_similarity = similarity
                best_topic_id = topic['topic_id']

        # Only return topic if similarity exceeds threshold
        if best_similarity >= self.similarity_threshold:
            return best_topic_id, best_similarity
        else:
            return None, best_similarity

    def assign_article_to_topic(
        self,
        article_id: int,
        topic_id: int,
        similarity_score: float,
        topic_date: datetime
    ) -> None:
        """
        Assign an article to a topic in the database

        Args:
            article_id: Article ID
            topic_id: Topic ID to assign to
            similarity_score: Cosine similarity score
            topic_date: Date of the topic
        """
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                # Insert into topic_article_mapping
                cur.execute(
                    """
                    INSERT INTO topic_article_mapping (
                        topic_id, article_id, similarity_score, topic_date
                    )
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (topic_id, article_id) DO NOTHING
                    """,
                    (topic_id, article_id, similarity_score, topic_date)
                )

                # Update topic's last_updated timestamp
                cur.execute(
                    """
                    UPDATE topic
                    SET last_updated = NOW()
                    WHERE topic_id = %s
                    """,
                    (topic_id,)
                )

        logger.debug(f"Assigned article {article_id} to topic {topic_id} (similarity: {similarity_score:.3f})")

    def add_to_pending(
        self,
        article_id: int,
        reason: str,
        max_similarity: float
    ) -> None:
        """
        Add article to pending pool (unmatched articles)

        Args:
            article_id: Article ID
            reason: Reason for pending (e.g., 'low_similarity')
            max_similarity: Highest similarity score found
        """
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO pending_articles (
                        article_id, reason, max_similarity
                    )
                    VALUES (%s, %s, %s)
                    ON CONFLICT (article_id) DO UPDATE
                    SET reason = EXCLUDED.reason,
                        max_similarity = EXCLUDED.max_similarity,
                        added_at = NOW()
                    """,
                    (article_id, reason, max_similarity)
                )

        logger.debug(f"Added article {article_id} to pending (reason: {reason}, max_similarity: {max_similarity:.3f})")

    def update_topic_centroids(self, topic_ids: List[int]) -> None:
        """
        Recalculate centroids for topics that received new articles

        Args:
            topic_ids: List of topic IDs to update
        """
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                for topic_id in topic_ids:
                    # Get all article embeddings for this topic
                    cur.execute(
                        """
                        SELECT a.embedding::text as embedding_text
                        FROM topic_article_mapping tam
                        JOIN article a ON tam.article_id = a.article_id
                        WHERE tam.topic_id = %s
                          AND a.embedding IS NOT NULL
                        """,
                        (topic_id,)
                    )
                    results = cur.fetchall()

                    if not results:
                        continue

                    # Parse embeddings
                    embeddings = []
                    for row in results:
                        embedding_str = row['embedding_text'].strip('[]')
                        embedding = np.array([float(x) for x in embedding_str.split(',')])
                        embeddings.append(embedding)

                    # Calculate new centroid (mean of all embeddings)
                    embeddings_matrix = np.array(embeddings)
                    centroid = np.mean(embeddings_matrix, axis=0)

                    # Normalize centroid
                    centroid_normalized = centroid / np.linalg.norm(centroid)

                    # Convert to list for storage
                    centroid_list = centroid_normalized.tolist()

                    # Update topic centroid
                    cur.execute(
                        """
                        UPDATE topic
                        SET centroid_embedding = %s::vector,
                            last_updated = NOW()
                        WHERE topic_id = %s
                        """,
                        (centroid_list, topic_id)
                    )

                    logger.debug(f"Updated centroid for topic {topic_id} with {len(embeddings)} articles")

    def run_incremental_assignment(
        self,
        news_date: Optional[datetime] = None,
        since_minutes: int = 30
    ) -> Dict:
        """
        Main function: Assign new articles to existing topics

        Args:
            news_date: Date to assign articles for (default: today)
            since_minutes: Look back window for new articles (default: 30)

        Returns:
            Dict with assignment statistics
        """
        if news_date is None:
            news_date = datetime.now().date()

        logger.info(f"Starting incremental assignment for {news_date}")

        # Step 1: Get new articles
        new_articles = self.get_new_articles(since_minutes=since_minutes)

        if not new_articles:
            logger.info("No new articles to assign")
            return {
                'success': True,
                'news_date': news_date.isoformat(),
                'new_articles': 0,
                'assigned': 0,
                'pending': 0
            }

        # Step 2: Get active topics
        active_topics = self.get_active_topics(news_date)

        if not active_topics:
            logger.warning(f"No active topics found for {news_date}")
            # Add all articles to pending
            for article in new_articles:
                self.add_to_pending(article['article_id'], 'no_topics', 0.0)

            return {
                'success': True,
                'news_date': news_date.isoformat(),
                'new_articles': len(new_articles),
                'assigned': 0,
                'pending': len(new_articles)
            }

        # Step 3: Assign each article
        assigned_count = 0
        pending_count = 0
        updated_topics = set()

        for article in new_articles:
            best_topic_id, best_similarity = self.find_best_topic(
                article['embedding'],
                active_topics
            )

            if best_topic_id:
                # Assign to topic
                self.assign_article_to_topic(
                    article['article_id'],
                    best_topic_id,
                    best_similarity,
                    news_date
                )
                assigned_count += 1
                updated_topics.add(best_topic_id)

                logger.info(
                    f"✅ Article {article['article_id']} → Topic {best_topic_id} "
                    f"(similarity: {best_similarity:.3f})"
                )
            else:
                # Add to pending
                self.add_to_pending(
                    article['article_id'],
                    'low_similarity',
                    best_similarity
                )
                pending_count += 1

                logger.info(
                    f"⏳ Article {article['article_id']} → Pending "
                    f"(max_similarity: {best_similarity:.3f})"
                )

        # Step 4: Update centroids for modified topics
        if updated_topics:
            logger.info(f"Updating centroids for {len(updated_topics)} topics")
            self.update_topic_centroids(list(updated_topics))

        result = {
            'success': True,
            'news_date': news_date.isoformat(),
            'new_articles': len(new_articles),
            'assigned': assigned_count,
            'pending': pending_count,
            'updated_topics': len(updated_topics)
        }

        logger.info(
            f"Incremental assignment complete: {assigned_count} assigned, "
            f"{pending_count} pending, {len(updated_topics)} topics updated"
        )

        return result


def run_incremental_assignment(
    news_date: Optional[datetime] = None,
    since_minutes: int = 30,
    similarity_threshold: float = 0.65
) -> Dict:
    """
    Convenience function to run incremental assignment

    Args:
        news_date: Date to assign articles for
        since_minutes: Look back window for new articles
        similarity_threshold: Minimum similarity to assign

    Returns:
        Results dictionary
    """
    assigner = IncrementalAssigner(similarity_threshold=similarity_threshold)
    return assigner.run_incremental_assignment(news_date, since_minutes)
