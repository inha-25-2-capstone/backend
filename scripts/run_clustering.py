#!/usr/bin/env python3
"""
Script to run topic clustering.

This script clusters articles with embeddings into topics.
Can be run manually or scheduled as a cron job.
"""
import sys
from pathlib import Path
from datetime import datetime, timedelta

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.services.clustering import cluster_topics_for_date
from src.utils.logger import setup_logger

logger = setup_logger("run_clustering", level="INFO")


def main():
    """Run topic clustering."""
    logger.info("=" * 80)
    logger.info("TOPIC CLUSTERING")
    logger.info("=" * 80)

    # Parse command-line arguments
    if len(sys.argv) > 1:
        # Date provided as argument (YYYY-MM-DD)
        try:
            news_date = datetime.strptime(sys.argv[1], "%Y-%m-%d")
            logger.info(f"Clustering topics for date: {news_date.date()}")
        except ValueError:
            logger.error(f"Invalid date format: {sys.argv[1]}. Use YYYY-MM-DD")
            return 1
    else:
        # Default: yesterday (since news cycle cutoff is 5:00 AM)
        news_date = datetime.now() - timedelta(days=1)
        news_date = news_date.replace(hour=0, minute=0, second=0, microsecond=0)
        logger.info(f"No date provided. Using yesterday: {news_date.date()}")

    # Optional: algorithm parameter (from env or command line)
    import os
    algorithm = os.environ.get('CLUSTERING_ALGORITHM', 'hierarchical')

    if len(sys.argv) > 2:
        algorithm = sys.argv[2].lower()
        if algorithm not in ['kmeans', 'dbscan', 'hierarchical']:
            logger.error(f"Invalid algorithm: {algorithm}. Use 'kmeans', 'dbscan', or 'hierarchical'")
            return 1

    logger.info(f"Using algorithm: {algorithm}")

    # Optional: number of topics (read from env or command line)
    n_topics = int(os.environ.get('CLUSTERING_TOP_N', '7'))
    if len(sys.argv) > 3:
        try:
            n_topics = int(sys.argv[3])
            logger.info(f"Number of topics (from argument): {n_topics}")
        except ValueError:
            logger.error(f"Invalid n_topics: {sys.argv[3]}. Must be an integer")
            return 1
    else:
        logger.info(f"Number of topics (from env): {n_topics}")

    try:
        # Run clustering
        result = cluster_topics_for_date(
            news_date=news_date,
            n_topics=n_topics,
            algorithm=algorithm
        )

        # Display results
        logger.info("\n" + "=" * 80)
        logger.info("CLUSTERING RESULTS")
        logger.info("=" * 80)

        if result['success']:
            logger.info(f" Success!")
            logger.info(f"  Date: {result['news_date']}")
            logger.info(f"  Articles processed: {result['articles_found']}")
            logger.info(f"  Topics created: {result['topics_created']}")
            logger.info(f"  Silhouette score: {result['silhouette_score']:.3f}")
            logger.info(f"  Algorithm: {result['algorithm']}")
            logger.info(f"  Topic IDs: {result['topic_ids']}")

            # Display topics
            logger.info("\n" + "=" * 80)
            logger.info("CREATED TOPICS")
            logger.info("=" * 80)

            from src.models.database import get_db_cursor

            with get_db_cursor() as cur:
                cur.execute(
                    """
                    SELECT
                        t.topic_id,
                        t.topic_rank,
                        t.topic_title,
                        t.article_count,
                        a.title as main_article_title
                    FROM topic t
                    JOIN article a ON t.main_article_id = a.article_id
                    WHERE t.topic_date = %s
                    ORDER BY t.topic_rank
                    """,
                    (news_date,)
                )
                topics = cur.fetchall()

                for topic in topics:
                    logger.info(
                        f"\nTopic {topic['topic_id']} (Rank {topic['topic_rank']}):"
                    )
                    logger.info(f"  Title: {topic['topic_title'][:80]}...")
                    logger.info(f"  Articles: {topic['article_count']}")
                    logger.info(f"  Main: {topic['main_article_title'][:80]}...")

            logger.info("\n" + "=" * 80)
            logger.info(" CLUSTERING COMPLETED SUCCESSFULLY")
            logger.info("=" * 80)
            return 0

        else:
            logger.error(f" Clustering failed")
            logger.error(f"  Error: {result.get('error', 'Unknown error')}")
            logger.error(f"  Articles found: {result.get('articles_found', 0)}")
            logger.info("\n" + "=" * 80)
            logger.info(" CLUSTERING FAILED")
            logger.info("=" * 80)
            return 1

    except Exception as e:
        logger.error(f" Clustering failed with exception: {e}")
        import traceback
        traceback.print_exc()
        logger.info("\n" + "=" * 80)
        logger.info(" CLUSTERING FAILED")
        logger.info("=" * 80)
        return 1


if __name__ == "__main__":
    sys.exit(main())
