"""
Celery Tasks for Asynchronous Processing
Handles batch AI processing (summarization + embedding + stance) and topic clustering
"""
from typing import List
import os
from datetime import datetime
from src.workers.celery_app import celery_app
from src.services.ai_client import create_ai_client, ArticleInput
from src.services.clustering import cluster_topics_for_date
from src.services.incremental_assignment import IncrementalAssigner
from src.models.database import get_db_connection, ArticleRepository
from src.utils.logger import setup_logger

logger = setup_logger()

# AI Service configuration from environment
AI_SERVICE_URL = os.getenv("AI_SERVICE_URL", "https://zedwrkc-news-stance-detection.hf.space")
AI_SERVICE_TIMEOUT = int(os.getenv("AI_SERVICE_TIMEOUT", "120"))


@celery_app.task(
    bind=True,
    max_retries=3,
    default_retry_delay=60
)
def process_articles_batch(self, article_ids: List[int]):
    """
    Process batch of articles through AI service

    Pipeline:
    1. Fetch articles from database
    2. Send to AI service (Summary + Embedding + Stance)
    3. Save results to database

    Args:
        article_ids: List of article IDs to process

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
            if article and article.get('content'):
                articles_data.append(ArticleInput(
                    article_id=article_id,
                    content=article['content']
                ))
            else:
                logger.warning(f"Article {article_id} not found or has no content")

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
    default_retry_delay=300
)
def cluster_daily_topics_task(self, news_date_str: str, n_topics: int = 7, algorithm: str = 'kmeans'):
    """
    Cluster articles into topics for a specific date

    This task should run after AI processing completes for the day.
    Typically scheduled via cron after the daily scraping and AI processing.

    Args:
        news_date_str: Date string in format YYYY-MM-DD
        n_topics: Number of topics to generate (default: 7)
        algorithm: Clustering algorithm ('kmeans' or 'dbscan')

    Returns:
        dict: Clustering results
    """
    try:
        # Parse date
        news_date = datetime.strptime(news_date_str, "%Y-%m-%d")
        logger.info(f"Starting topic clustering task for {news_date_str}")

        # Run clustering
        result = cluster_topics_for_date(
            news_date=news_date,
            n_topics=n_topics,
            algorithm=algorithm
        )

        if result['success']:
            logger.info(
                f"Clustering completed successfully: "
                f"{result['topics_created']} topics from {result['articles_found']} articles"
            )
        else:
            logger.warning(
                f"Clustering failed: {result.get('error', 'Unknown error')}"
            )

        return result

    except ValueError as e:
        logger.error(f"Invalid date format: {news_date_str}. Use YYYY-MM-DD")
        return {
            'success': False,
            'error': f'Invalid date format: {e}'
        }

    except Exception as e:
        logger.error(f"Clustering task failed: {e}", exc_info=True)
        # Retry with exponential backoff
        raise self.retry(exc=e, countdown=2 ** self.request.retries)


@celery_app.task(
    bind=True,
    max_retries=3,
    default_retry_delay=60
)
def incremental_assign_articles(self, news_date_str: str = None, since_minutes: int = 30):
    """
    Incrementally assign new articles to existing topics

    This task runs after AI processing to assign newly processed articles
    to existing topics based on centroid similarity.

    Args:
        news_date_str: Date string in format YYYY-MM-DD (default: today)
        since_minutes: Look back window for new articles (default: 30)

    Returns:
        dict: Assignment statistics
    """
    try:
        # Parse date or use today
        if news_date_str:
            news_date = datetime.strptime(news_date_str, "%Y-%m-%d").date()
        else:
            news_date = datetime.now().date()

        logger.info(f"Starting incremental assignment for {news_date}")

        # Run incremental assignment
        with get_db_connection() as conn:
            assigner = IncrementalAssigner(conn)
            result = assigner.run_incremental_assignment(
                news_date=news_date,
                since_minutes=since_minutes
            )

        if result['success']:
            logger.info(
                f"Incremental assignment completed: "
                f"{result['assigned']} assigned, {result['pending']} pending, "
                f"{result.get('updated_topics', 0)} topics updated"
            )
        else:
            logger.warning(f"Incremental assignment had issues")

        return result

    except ValueError as e:
        logger.error(f"Invalid date format: {news_date_str}. Use YYYY-MM-DD")
        return {
            'success': False,
            'error': f'Invalid date format: {e}'
        }

    except Exception as e:
        logger.error(f"Incremental assignment task failed: {e}", exc_info=True)
        # Retry with exponential backoff
        raise self.retry(exc=e, countdown=2 ** self.request.retries)
