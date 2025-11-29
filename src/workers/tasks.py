"""
Celery Tasks for Asynchronous Processing
Handles batch AI processing (summarization + embedding + stance)
"""
from typing import List
import os
import json
from datetime import datetime
import redis
from src.workers.celery_app import celery_app
from src.services.ai_client import create_ai_client, ArticleInput
from src.models.database import ArticleRepository, StanceRepository
from src.utils.logger import setup_logger

logger = setup_logger()

# AI Service configuration from environment
AI_SERVICE_URL = os.getenv("AI_SERVICE_URL", "https://gaaahee-news-stance-detection.hf.space")
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

                # Save stance analysis result
                if result.stance:
                    try:
                        StanceRepository.insert(
                            article_id=result.article_id,
                            stance_label=result.stance['stance_label'],
                            prob_positive=result.stance['prob_positive'],
                            prob_neutral=result.stance['prob_neutral'],
                            prob_negative=result.stance['prob_negative'],
                            stance_score=result.stance['stance_score']
                        )
                        logger.debug(
                            f"Article {result.article_id} stance saved: "
                            f"{result.stance['stance_label']} (score: {result.stance['stance_score']:.4f})"
                        )
                    except Exception as e:
                        logger.error(f"Failed to save stance for article {result.article_id}: {e}")
                        # Don't fail the whole batch if stance saving fails

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
                    logger.info(f"   Waiting 60 seconds for final batch to complete...")

                    # Trigger BERTopic with full article clustering (no limit)
                    bertopic_clustering_task.apply_async(
                        args=[news_date_str, None],  # None = 전체 기사 클러스터링 ⭐
                        countdown=60  # 60초 후 실행 (마지막 배치 완료 대기) ⭐
                    )

                    logger.info(f"   BERTopic will cluster ALL articles with embeddings for {news_date_str}")

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
def bertopic_clustering_task(self, news_date_str: str = None, limit: int = None):
    """
    BERTopic clustering task with Improved Noun-only tokenizer

    Fetches articles with embeddings from DB and runs improved BERTopic clustering
    with noun-only extraction for better topic titles (3-6 words).

    Args:
        news_date_str: Optional date string (YYYY-MM-DD) to filter articles
        limit: Maximum number of articles to cluster (None = all articles) ⭐

    Returns:
        dict: Clustering results with topics saved to database
    """
    from datetime import datetime
    from src.services.bertopic_service import fetch_articles_with_embeddings
    from src.models.database import get_db_connection
    from src.services.ai_client import create_ai_client

    try:
        # Parse date if provided
        news_date = None
        if news_date_str:
            news_date = datetime.strptime(news_date_str, "%Y-%m-%d").date()
            if limit:
                logger.info(f"Starting BERTopic clustering for {news_date_str} (limit: {limit})")
            else:
                logger.info(f"Starting BERTopic clustering for {news_date_str} (ALL articles) ⭐")
        else:
            if limit:
                logger.info(f"Starting BERTopic clustering for recent {limit} articles")
            else:
                logger.info(f"Starting BERTopic clustering for ALL recent articles ⭐")

        # Fetch articles with embeddings from DB
        articles, embeddings, doc_texts = fetch_articles_with_embeddings(news_date, limit)

        if not articles or embeddings is None:
            logger.warning("No articles with embeddings found for BERTopic clustering")
            return {
                'success': False,
                'error': 'No articles with embeddings found',
                'total_articles': 0
            }

        # Prepare data for HF Spaces API
        article_ids = [a['article_id'] for a in articles]
        embeddings_list = embeddings.tolist()

        logger.info(f"Sending {len(articles)} articles to HF Spaces for Improved BERTopic clustering")

        # Call HF Spaces Improved BERTopic clustering API (with visualization)
        with create_ai_client(base_url=AI_SERVICE_URL, timeout=AI_SERVICE_TIMEOUT) as ai_client:
            result = ai_client.cluster_topics_improved(
                embeddings=embeddings_list,
                texts=doc_texts,
                article_ids=article_ids,
                news_date=str(news_date or datetime.now().date()),
                min_topic_size=5,
                nr_topics="auto",
                include_visualization=True,  # Request visualization with clustering ⭐
                viz_dpi=150,
                viz_width=1400,
                viz_height=1400
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

                    # DEBUG: Check raw values from HF Spaces
                    logger.info(f"RAW HF SPACES DATA - Topic {topic['topic_id']}: article_count={topic['article_count']}, cluster_score={cluster_score}, len(article_ids)={len(topic['article_ids'])}")

                    # DEBUG: Log to check if similarity_scores is populated
                    logger.info(f"DEBUG - Topic {topic['topic_id']}: article_count={article_count}, len(article_ids)={len(topic['article_ids'])}, similarity_scores count={len(similarity_scores)}")

                    # DEBUG: Check similarity_scores keys type and sample values
                    if similarity_scores:
                        sample_keys = list(similarity_scores.keys())[:3]
                        sample_items = {k: similarity_scores[k] for k in sample_keys}
                        logger.info(f"DEBUG - similarity_scores sample: {sample_items}")
                        logger.info(f"DEBUG - similarity_scores keys type: {type(sample_keys[0]) if sample_keys else 'N/A'}")

                    # DEBUG: Log the actual article_ids to compare
                    logger.info(f"DEBUG - First 3 article_ids from HF Spaces: {topic['article_ids'][:3]}")

                    logger.info(f"Saving Topic {topic['topic_id']}: {topic_title} (Rank {topic_rank}, {article_count} articles)")

                    # Prepare centroid embedding for DB (pgvector format)
                    centroid_str = None
                    if centroid:
                        centroid_str = '[' + ','.join(map(str, centroid)) + ']'

                    # Prepare keywords for DB (JSONB format - Top 10 for word cloud)
                    keywords_json = None
                    if 'keywords' in topic and topic['keywords']:
                        # Store Top 10 keywords with scores
                        top_keywords = topic['keywords'][:10]
                        keywords_json = json.dumps(top_keywords, ensure_ascii=False)
                        logger.debug(f"Topic {topic['topic_id']}: storing {len(top_keywords)} keywords")

                    # Insert topic with centroid, rank, cluster score, and keywords
                    # Note: article_count is manually managed (triggers removed)

                    # DEBUG: Log exact values being passed to INSERT
                    logger.info(f"PRE-INSERT VALUES - Topic {topic['topic_id']}: article_count={article_count}, cluster_score={cluster_score}, topic_rank={topic_rank}, keywords={len(topic.get('keywords', []))}")

                    cursor.execute(
                        """
                        INSERT INTO topic (
                            topic_date, topic_title, main_article_id, article_count,
                            topic_rank, cluster_score, centroid_embedding, keywords, created_at
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
                        RETURNING topic_id
                        """,
                        (result_date, topic_title, main_article_id, article_count,
                         topic_rank, cluster_score, centroid_str, keywords_json)
                    )

                    db_topic_id = cursor.fetchone()[0]
                    topics_saved += 1

                    # DEBUG: Verify what was actually saved
                    cursor.execute("SELECT article_count, cluster_score FROM topic WHERE topic_id = %s", (db_topic_id,))
                    saved_article_count, saved_cluster_score = cursor.fetchone()
                    logger.info(f"VERIFY DB - Topic {db_topic_id}: INSERTED article_count={article_count}, cluster_score={cluster_score} → SAVED article_count={saved_article_count}, cluster_score={saved_cluster_score}")

                    # Insert topic-article mappings with real similarity scores
                    for article_id in topic['article_ids']:
                        # Get similarity score for this article (default to 1.0 if not found)
                        # Note: HF Spaces returns string keys, so convert article_id to string
                        similarity_score = similarity_scores.get(str(article_id), 1.0)

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

        # Save visualization from clustering result (no separate API call)
        try:
            visualization_b64 = result.get('visualization')

            if visualization_b64:
                import base64
                logger.info("Saving visualization from clustering result...")

                # Decode base64 to bytes
                image_bytes = base64.b64decode(visualization_b64)

                # Save to database (UPSERT - always id=1)
                with get_db_connection() as conn:
                    with conn.cursor() as cursor:
                        cursor.execute(
                            """
                            INSERT INTO topic_visualization (id, news_date, image_data, dpi, article_count, created_at)
                            VALUES (1, %s, %s, %s, %s, NOW())
                            ON CONFLICT (id) DO UPDATE SET
                                news_date = EXCLUDED.news_date,
                                image_data = EXCLUDED.image_data,
                                dpi = EXCLUDED.dpi,
                                article_count = EXCLUDED.article_count,
                                created_at = NOW()
                            """,
                            (result_date, image_bytes, 150, len(articles))
                        )
                        conn.commit()

                logger.info(f"Visualization saved to database ({len(image_bytes)} bytes)")
            else:
                logger.warning("No visualization in clustering result")

        except Exception as viz_error:
            logger.warning(f"Failed to save visualization (non-critical): {viz_error}")

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
