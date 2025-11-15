"""
Celery Tasks for Asynchronous Processing
Handles batch AI processing (summarization + embedding + stance)
"""
from typing import List
import os
from datetime import datetime
import redis
from src.workers.celery_app import celery_app
from src.services.ai_client import create_ai_client, ArticleInput
from src.models.database import ArticleRepository
from src.utils.logger import setup_logger

logger = setup_logger()

# AI Service configuration from environment
AI_SERVICE_URL = os.getenv("AI_SERVICE_URL", "https://zedwrkc-news-stance-detection.hf.space")
AI_SERVICE_TIMEOUT = int(os.getenv("AI_SERVICE_TIMEOUT", "120"))

# Redis client for batch coordination
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
redis_client = redis.from_url(REDIS_URL, decode_responses=True)


@celery_app.task(
    bind=True,
    max_retries=3,
    default_retry_delay=60
)
def process_articles_batch(self, article_ids: List[int], target_news_date: str = None):
    """
    Process batch of articles through AI service

    Pipeline:
    1. Fetch articles from database
    2. Send to AI service (Summary + Embedding + Stance)
    3. Save results to database

    Args:
        article_ids: List of article IDs to process
        target_news_date: Target news_date for Redis counter (YYYY-MM-DD format)

    Returns:
        dict: Processing statistics
    """
    try:
        logger.info(f"Processing batch of {len(article_ids)} articles")

        # Validate batch size
        if len(article_ids) > 50:
            logger.error(f"Batch size ({len(article_ids)}) exceeds maximum (50)")
            return {
                "status": "error",
                "message": "Batch size exceeds maximum",
                "processed": 0,
                "successful": 0,
                "failed": len(article_ids)
            }

        # Step 1: Fetch articles from database
        articles_data = []
        for article_id in article_ids:
            article = ArticleRepository.get_by_id(article_id)
            if article and article.get('content') and article.get('title'):
                articles_data.append(ArticleInput(
                    article_id=article_id,
                    title=article['title'],
                    content=article['content']
                ))
            else:
                logger.warning(f"Article {article_id} not found or missing content/title")

        if not articles_data:
            logger.warning("No valid articles to process")
            return {
                "status": "error",
                "message": "No valid articles found",
                "processed": 0,
                "successful": 0,
                "failed": len(article_ids)
            }

        logger.info(f"Fetched {len(articles_data)} articles from database")

        # Step 2: Process through AI service
        # Note: warmup is handled automatically in process_batch
        with create_ai_client(base_url=AI_SERVICE_URL, timeout=AI_SERVICE_TIMEOUT) as ai_client:
            # Process batch (warmup handled internally)
            results = ai_client.process_batch(
                articles=articles_data,
                max_summary_length=300,
                min_summary_length=150
            )

        # Step 3: Save results to database
        successful_count = 0
        failed_count = 0

        for result in results:
            try:
                if result.error:
                    logger.error(f"Article {result.article_id} failed: {result.error}")
                    failed_count += 1
                    continue

                # Update article with summary and embedding
                update_data = {}

                if result.summary:
                    update_data['summary'] = result.summary

                if result.embedding:
                    # Convert list to pgvector format: [0.1, 0.2, ...]
                    embedding_str = '[' + ','.join(map(str, result.embedding)) + ']'
                    update_data['embedding'] = embedding_str

                if update_data:
                    ArticleRepository.update_summary_and_embedding(
                        article_id=result.article_id,
                        **update_data
                    )
                    successful_count += 1
                    logger.debug(f"Article {result.article_id} updated successfully")

                # TODO: Save stance to stance_analysis table when model ready
                # if result.stance:
                #     stance_repo.insert(...)

            except Exception as e:
                logger.error(f"Failed to save article {result.article_id}: {e}")
                failed_count += 1

        logger.info(
            f"Batch processing completed: "
            f"{successful_count} successful, {failed_count} failed"
        )

        # Redis counter: Check if all batches are complete
        try:
            # Use target_news_date if provided, otherwise fallback to first article's date
            news_date_str = None
            if target_news_date:
                news_date_str = target_news_date
                logger.debug(f"Using target_news_date from parameter: {news_date_str}")
            elif article_ids:
                first_article = ArticleRepository.get_by_id(article_ids[0])
                if first_article and first_article.get('news_date'):
                    news_date_str = str(first_article['news_date'])
                    logger.debug(f"Using news_date from first article: {news_date_str}")

            if news_date_str:
                # Redis keys for this news_date
                counter_key = f"ai_batch_completed:{news_date_str}"
                total_key = f"ai_batch_total:{news_date_str}"

                # Increment completed counter
                completed = redis_client.incr(counter_key)
                total = redis_client.get(total_key)

                logger.info(f"AI batches progress: {completed}/{total} completed for {news_date_str}")

                # If all batches complete, trigger BERTopic
                if total and int(completed) >= int(total):
                    logger.info(f"🎯 All AI batches complete! Triggering BERTopic clustering...")
                    bertopic_clustering_task.apply_async(
                        args=[news_date_str, 200],
                        countdown=10  # 10초 후 실행 (안전 마진)
                    )
                    # Clean up Redis keys
                    redis_client.delete(counter_key)
                    redis_client.delete(total_key)
        except Exception as e:
            logger.warning(f"Redis counter error (non-critical): {e}")

        return {
            "status": "success",
            "processed": len(results),
            "successful": successful_count,
            "failed": failed_count
        }

    except Exception as e:
        logger.error(f"Batch processing task failed: {e}", exc_info=True)
        # Retry with exponential backoff
        raise self.retry(exc=e, countdown=2 ** self.request.retries)


@celery_app.task(
    bind=True,
    max_retries=3,
    default_retry_delay=60
)
def bertopic_clustering_task(self, news_date_str: str = None, limit: int = 200):
    """
    BERTopic clustering task (runs in backend, not HF Spaces)

    Fetches articles with embeddings from DB and runs sklearn BERTopic clustering.

    Args:
        news_date_str: Optional date string (YYYY-MM-DD) to filter articles
        limit: Maximum number of articles to cluster

    Returns:
        dict: Clustering results with topics saved to database
    """
    from datetime import datetime
    from src.services.bertopic_service import run_bertopic_clustering
    from src.models.database import get_db_connection

    try:
        # Parse date if provided
        news_date = None
        if news_date_str:
            news_date = datetime.strptime(news_date_str, "%Y-%m-%d").date()
            logger.info(f"Starting BERTopic clustering for {news_date_str}")
        else:
            logger.info(f"Starting BERTopic clustering for recent {limit} articles")

        # Run clustering
        result = run_bertopic_clustering(
            news_date=news_date,
            limit=limit,
            min_topic_size=5,
            nr_topics="auto"
        )

        if not result['success']:
            logger.warning(f"Clustering failed: {result.get('error')}")
            return result

        logger.info(
            f"Clustering successful: {result['total_topics']} topics from "
            f"{result['total_articles']} articles"
        )

        # Save topics to database
        topics_saved = 0
        mappings_saved = 0

        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                # Get news_date from result
                result_date = result['news_date']

                # Clear existing topics for this date
                cursor.execute(
                    """
                    DELETE FROM topic_article_mapping
                    WHERE topic_id IN (SELECT topic_id FROM topic WHERE topic_date = %s)
                    """,
                    (result_date,)
                )
                cursor.execute("DELETE FROM topic WHERE topic_date = %s", (result_date,))

                # Insert new topics (skip outliers topic_id=-1)
                for topic in result['topics']:
                    if topic['topic_id'] == -1:
                        logger.info(f"Skipping outlier topic ({topic['article_count']} articles)")
                        continue

                    topic_title = topic['topic_title']
                    article_count = topic['article_count']
                    main_article_id = topic['article_ids'][0] if topic['article_ids'] else None
                    centroid = topic.get('centroid')  # Get centroid embedding
                    similarity_scores = topic.get('similarity_scores', {})  # Get similarity scores dict
                    topic_rank = topic.get('topic_rank')  # Get rank (1-10 or None)
                    cluster_score = topic.get('cluster_score')  # Get cluster score

                    logger.info(f"Saving Topic {topic['topic_id']}: {topic_title} (Rank {topic_rank}, {article_count} articles)")

                    # Prepare centroid embedding for DB (pgvector format)
                    centroid_str = None
                    if centroid:
                        centroid_str = '[' + ','.join(map(str, centroid)) + ']'

                    # Insert topic with centroid, rank, and cluster score
                    # Note: article_count is manually managed (triggers removed)
                    cursor.execute(
                        """
                        INSERT INTO topic (
                            topic_date, topic_title, main_article_id, article_count,
                            topic_rank, cluster_score, centroid_embedding, created_at
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
                        RETURNING topic_id
                        """,
                        (result_date, topic_title, main_article_id, article_count,
                         topic_rank, cluster_score, centroid_str)
                    )

                    db_topic_id = cursor.fetchone()[0]
                    topics_saved += 1

                    # Insert topic-article mappings with real similarity scores
                    for article_id in topic['article_ids']:
                        # Get similarity score for this article (default to 1.0 if not found)
                        similarity_score = similarity_scores.get(article_id, 1.0)

                        cursor.execute(
                            """
                            INSERT INTO topic_article_mapping (
                                topic_id, article_id, similarity_score, topic_date
                            )
                            VALUES (%s, %s, %s, %s)
                            ON CONFLICT (topic_id, article_id) DO NOTHING
                            """,
                            (db_topic_id, article_id, similarity_score, result_date)
                        )
                        mappings_saved += 1

                conn.commit()

        logger.info(f"Saved {topics_saved} topics and {mappings_saved} article mappings to database")

        return {
            'success': True,
            'topics_saved': topics_saved,
            'mappings_saved': mappings_saved,
            'total_topics': result['total_topics'],
            'total_articles': result['total_articles'],
            'outliers': result['outliers'],
            'news_date': str(result_date)
        }

    except Exception as e:
        logger.error(f"BERTopic clustering task failed: {e}", exc_info=True)
        # Retry with exponential backoff
        raise self.retry(exc=e, countdown=2 ** self.request.retries)
