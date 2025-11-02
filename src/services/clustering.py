"""
Topic Clustering Service
Uses pgvector cosine similarity to cluster articles by embeddings
"""
import numpy as np
from typing import List, Dict, Optional, Tuple
from datetime import datetime
from sklearn.cluster import KMeans, DBSCAN, AgglomerativeClustering
from sklearn.metrics import silhouette_score
import logging

from src.models.database import get_db_cursor, get_db_connection
from src.utils.logger import setup_logger
from src.utils.embeddings import parse_embedding_string, normalize_vector
from src.services.topic_generation import generate_topics_from_clusters

logger = setup_logger(__name__)


class TopicClusterer:
    """
    Clusters articles into topics based on embedding similarity.
    Uses pgvector for efficient cosine similarity search.
    """

    def __init__(self, n_topics: int = 7, min_articles_per_topic: int = 1):
        """
        Initialize topic clusterer.

        Args:
            n_topics: Number of topics to generate (default: 7)
            min_articles_per_topic: Minimum articles required per topic (default: 1)
        """
        self.n_topics = n_topics
        self.min_articles_per_topic = min_articles_per_topic

    def get_articles_with_embeddings(
        self, news_date: datetime
    ) -> List[Dict]:
        """
        Fetch articles with embeddings for a specific news date.

        Args:
            news_date: Date to fetch articles for

        Returns:
            List of article dictionaries with id, title, summary, embedding
        """
        with get_db_cursor() as cur:
            cur.execute(
                """
                SELECT
                    article_id,
                    title,
                    summary,
                    embedding::text as embedding_text
                FROM article
                WHERE news_date = %s
                AND embedding IS NOT NULL
                ORDER BY published_at DESC
                """,
                (news_date,)
            )
            results = cur.fetchall()

        articles = []
        for row in results:
            # Parse embedding vector from text format using utility function
            embedding = parse_embedding_string(row['embedding_text'])

            articles.append({
                'article_id': row['article_id'],
                'title': row['title'],
                'summary': row['summary'],
                'embedding': embedding
            })

        logger.info(f"Fetched {len(articles)} articles with embeddings for {news_date}")
        return articles

    def cluster_articles(
        self,
        articles: List[Dict],
        algorithm: str = 'kmeans'
    ) -> Tuple[List[int], float]:
        """
        Cluster articles using their embeddings.

        Args:
            articles: List of article dicts with 'embedding' key
            algorithm: 'kmeans' or 'dbscan'

        Returns:
            Tuple of (cluster_labels, silhouette_score)
        """
        if len(articles) < self.n_topics:
            logger.warning(
                f"Not enough articles ({len(articles)}) for {self.n_topics} topics. "
                f"Reducing to {len(articles)} topics."
            )
            n_clusters = max(1, len(articles))
        else:
            n_clusters = self.n_topics

        # Extract embeddings as numpy array
        embeddings = np.array([article['embedding'] for article in articles])

        # Normalize embeddings for cosine similarity using utility function
        from src.utils.embeddings import batch_normalize_vectors
        embeddings_normalized = batch_normalize_vectors([emb for emb in embeddings])

        if algorithm == 'kmeans':
            clusterer = KMeans(
                n_clusters=n_clusters,
                random_state=42,
                n_init=10
            )
            labels = clusterer.fit_predict(embeddings_normalized)

        elif algorithm == 'dbscan':
            # DBSCAN for density-based clustering
            clusterer = DBSCAN(
                eps=0.3,
                min_samples=self.min_articles_per_topic,
                metric='cosine'
            )
            labels = clusterer.fit_predict(embeddings_normalized)

        elif algorithm == 'hierarchical':
            # Hierarchical Agglomerative Clustering
            import os

            # Get parameters from environment
            distance_threshold = float(os.environ.get('CLUSTERING_DISTANCE_THRESHOLD', '0.5'))
            min_clusters = int(os.environ.get('CLUSTERING_MIN_TOPICS', '5'))
            max_clusters = int(os.environ.get('CLUSTERING_MAX_TOPICS', '10'))

            logger.info(
                f"Hierarchical clustering with distance_threshold={distance_threshold}, "
                f"range=[{min_clusters}, {max_clusters}]"
            )

            # Try with distance threshold first
            clusterer = AgglomerativeClustering(
                n_clusters=None,
                distance_threshold=distance_threshold,
                metric='cosine',
                linkage='average'
            )
            labels = clusterer.fit_predict(embeddings_normalized)

            n_clusters_found = len(set(labels))

            # If outside desired range, force cluster count
            if n_clusters_found < min_clusters:
                logger.warning(
                    f"Found {n_clusters_found} clusters (< {min_clusters}). "
                    f"Re-clustering with n_clusters={min_clusters}"
                )
                clusterer = AgglomerativeClustering(
                    n_clusters=min_clusters,
                    metric='cosine',
                    linkage='average'
                )
                labels = clusterer.fit_predict(embeddings_normalized)

            elif n_clusters_found > max_clusters:
                logger.warning(
                    f"Found {n_clusters_found} clusters (> {max_clusters}). "
                    f"Re-clustering with n_clusters={max_clusters}"
                )
                clusterer = AgglomerativeClustering(
                    n_clusters=max_clusters,
                    metric='cosine',
                    linkage='average'
                )
                labels = clusterer.fit_predict(embeddings_normalized)

        else:
            raise ValueError(f"Unknown algorithm: {algorithm}")

        # Calculate silhouette score (if we have enough clusters)
        if len(set(labels)) > 1 and len(articles) > len(set(labels)):
            score = silhouette_score(embeddings_normalized, labels, metric='cosine')
        else:
            score = 0.0

        logger.info(
            f"Clustered {len(articles)} articles into {len(set(labels))} clusters "
            f"(algorithm: {algorithm}, silhouette score: {score:.3f})"
        )

        return labels.tolist(), score

    def select_representative_article(
        self,
        cluster_articles: List[Dict]
    ) -> int:
        """
        Select the most representative article from a cluster.
        Uses the article closest to the cluster centroid.

        Args:
            cluster_articles: List of articles in the cluster

        Returns:
            article_id of the representative article
        """
        if len(cluster_articles) == 1:
            return cluster_articles[0]['article_id']

        # Calculate centroid
        embeddings = np.array([article['embedding'] for article in cluster_articles])
        centroid = np.mean(embeddings, axis=0)

        # Normalize using utility function
        centroid_normalized = normalize_vector(centroid)
        from src.utils.embeddings import batch_normalize_vectors
        embeddings_normalized = batch_normalize_vectors([emb for emb in embeddings])

        # Find closest article to centroid (highest cosine similarity)
        similarities = np.dot(embeddings_normalized, centroid_normalized)
        representative_idx = np.argmax(similarities)

        return cluster_articles[representative_idx]['article_id']

    def calculate_similarity_scores(
        self,
        cluster_articles: List[Dict],
        representative_embedding: np.ndarray
    ) -> Dict[int, float]:
        """
        Calculate cosine similarity scores for all articles in cluster.

        Args:
            cluster_articles: Articles in the cluster
            representative_embedding: Embedding of representative article

        Returns:
            Dict mapping article_id to similarity score
        """
        representative_norm = representative_embedding / np.linalg.norm(representative_embedding)

        scores = {}
        for article in cluster_articles:
            embedding = article['embedding']
            embedding_norm = embedding / np.linalg.norm(embedding)

            # Cosine similarity
            similarity = float(np.dot(embedding_norm, representative_norm))
            scores[article['article_id']] = similarity

        return scores

    def save_topics_to_db(
        self,
        articles: List[Dict],
        cluster_labels: List[int],
        news_date: datetime,
        silhouette: float = 0.0
    ) -> List[int]:
        """
        Save clustered topics to database.

        Args:
            articles: List of articles
            cluster_labels: Cluster assignment for each article
            news_date: Date for topics
            silhouette: Silhouette score for clustering quality

        Returns:
            List of created topic_ids
        """
        # Group articles by cluster
        clusters = {}
        for article, label in zip(articles, cluster_labels):
            if label not in clusters:
                clusters[label] = []
            clusters[label].append(article)

        # Filter out small clusters
        valid_clusters = {
            label: cluster_articles
            for label, cluster_articles in clusters.items()
            if len(cluster_articles) >= self.min_articles_per_topic
        }

        if not valid_clusters:
            logger.warning(f"No valid clusters found for {news_date}")
            return []

        # Sort clusters by size (descending) and take top N
        sorted_clusters = sorted(
            valid_clusters.items(),
            key=lambda x: len(x[1]),
            reverse=True
        )[:self.n_topics]

        topic_ids = []

        # Generate topic titles using TF-IDF (via AI service)
        logger.info(f"Generating topic titles for {len(sorted_clusters)} clusters using TF-IDF...")
        try:
            # Prepare clusters for topic generation
            clusters_for_api = []
            for cluster_label, cluster_articles in sorted_clusters:
                # Take top 5 representative articles per cluster
                representative_articles = cluster_articles[:5]
                clusters_for_api.append({
                    "cluster_id": cluster_label,
                    "representative_articles": [
                        {
                            "title": article.get('title', ''),
                            "summary": article.get('summary', '')
                        }
                        for article in representative_articles
                    ]
                })

            # Call AI service to generate topics
            generated_topics = generate_topics_from_clusters(
                clusters=clusters_for_api,
                top_n_keywords=3,
                method="tfidf",  # TF-IDF is better for Korean
                use_phrases=True
            )

            # Create a mapping from cluster_id to topic_title
            topic_titles_map = {
                topic["cluster_id"]: topic["topic_title"]
                for topic in generated_topics
            }
            logger.info(f"✓ Generated {len(topic_titles_map)} topic titles")

        except Exception as e:
            logger.warning(f"Topic generation failed: {e}. Falling back to article titles.")
            topic_titles_map = {}

        with get_db_connection() as conn:
            with conn.cursor() as cur:
                # Delete existing topics for this date
                cur.execute(
                    "DELETE FROM topic WHERE topic_date = %s",
                    (news_date,)
                )
                logger.info(f"Deleted existing topics for {news_date}")

                # Create topics
                for rank, (cluster_label, cluster_articles) in enumerate(sorted_clusters, start=1):
                    # Select representative article
                    main_article_id = self.select_representative_article(cluster_articles)

                    # Get representative article's embedding
                    representative_article = next(
                        a for a in cluster_articles if a['article_id'] == main_article_id
                    )
                    representative_embedding = representative_article['embedding']

                    # Calculate centroid for incremental assignment
                    embeddings = np.array([article['embedding'] for article in cluster_articles])
                    centroid = np.mean(embeddings, axis=0)

                    # Normalize centroid
                    centroid_normalized = centroid / np.linalg.norm(centroid)

                    # Convert centroid to list for database storage
                    centroid_list = centroid_normalized.tolist()

                    # Use generated topic title or fall back to representative article title
                    topic_title = topic_titles_map.get(
                        cluster_label,
                        representative_article['title']  # Fallback
                    )

                    # Insert topic with centroid
                    # Note: main_stance defaults to '중립' until stance analysis is ready
                    # Note: article_count starts at 0, will be incremented by trigger
                    cur.execute(
                        """
                        INSERT INTO topic (
                            topic_date, topic_title, main_article_id,
                            topic_rank, article_count, main_stance, main_stance_score, cluster_score,
                            centroid_embedding, is_active
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        RETURNING topic_id
                        """,
                        (
                            news_date, topic_title, main_article_id, rank, 0,  # article_count=0, trigger will update
                            '중립', 0.0, silhouette,
                            centroid_list, True  # is_active=True for new topics
                        )
                    )
                    topic_id = cur.fetchone()[0]
                    topic_ids.append(topic_id)

                    logger.info(
                        f"Created topic {topic_id} (rank {rank}): {topic_title[:50]}... "
                        f"({len(cluster_articles)} articles, silhouette: {silhouette:.3f})"
                    )

                    # Calculate similarity scores
                    similarity_scores = self.calculate_similarity_scores(
                        cluster_articles,
                        representative_embedding
                    )

                    # Insert article mappings
                    for article in cluster_articles:
                        similarity_score = similarity_scores[article['article_id']]

                        cur.execute(
                            """
                            INSERT INTO topic_article_mapping (
                                topic_id, article_id, similarity_score, topic_date
                            )
                            VALUES (%s, %s, %s, %s)
                            """,
                            (topic_id, article['article_id'], similarity_score, news_date)
                        )

                    logger.debug(f"Mapped {len(cluster_articles)} articles to topic {topic_id}")

        logger.info(f"Saved {len(topic_ids)} topics for {news_date} with centroids")
        return topic_ids

    def cluster_daily_topics(
        self,
        news_date: datetime,
        algorithm: str = 'kmeans'
    ) -> Dict:
        """
        Main function: Cluster articles for a specific date into topics.

        Args:
            news_date: Date to cluster
            algorithm: Clustering algorithm ('kmeans' or 'dbscan')

        Returns:
            Dict with results summary
        """
        logger.info(f"Starting topic clustering for {news_date}")

        # Step 1: Fetch articles with embeddings
        articles = self.get_articles_with_embeddings(news_date)

        if not articles:
            logger.warning(f"No articles with embeddings found for {news_date}")
            return {
                'success': False,
                'error': 'No articles with embeddings',
                'articles_found': 0
            }

        if len(articles) < self.min_articles_per_topic:
            logger.warning(
                f"Not enough articles ({len(articles)}) for clustering. "
                f"Minimum required: {self.min_articles_per_topic}"
            )
            return {
                'success': False,
                'error': f'Insufficient articles (found {len(articles)}, need {self.min_articles_per_topic})',
                'articles_found': len(articles)
            }

        # Step 2: Cluster articles
        cluster_labels, silhouette = self.cluster_articles(articles, algorithm=algorithm)

        # Step 3: Save to database
        topic_ids = self.save_topics_to_db(articles, cluster_labels, news_date, silhouette)

        result = {
            'success': True,
            'news_date': news_date.isoformat(),
            'articles_found': len(articles),
            'topics_created': len(topic_ids),
            'topic_ids': topic_ids,
            'silhouette_score': silhouette,
            'algorithm': algorithm
        }

        logger.info(
            f"Clustering complete: {len(topic_ids)} topics created from {len(articles)} articles "
            f"(silhouette: {silhouette:.3f})"
        )

        return result


def cluster_topics_for_date(
    news_date: datetime,
    n_topics: int = 7,
    algorithm: str = 'kmeans'
) -> Dict:
    """
    Convenience function to cluster topics for a date.

    Args:
        news_date: Date to cluster
        n_topics: Number of topics to generate
        algorithm: Clustering algorithm

    Returns:
        Results dictionary
    """
    clusterer = TopicClusterer(n_topics=n_topics)
    return clusterer.cluster_daily_topics(news_date, algorithm=algorithm)
