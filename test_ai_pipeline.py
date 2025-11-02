"""
Test script for AI processing pipeline
Tests: Scraper → Celery Task → AI Service → Database
"""
import sys
import os
import time

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.models.database import get_db_connection, ArticleRepository
from src.services.ai_client import create_ai_client, ArticleInput
from src.utils.logger import setup_logger

logger = setup_logger("test_pipeline")

AI_SERVICE_URL = os.getenv("AI_SERVICE_URL", "https://zedwrkc-news-stance-detection.hf.space")


def test_ai_service_health():
    """Test 1: AI service health check"""
    logger.info("=" * 60)
    logger.info("TEST 1: AI Service Health Check")
    logger.info("=" * 60)

    try:
        with create_ai_client(AI_SERVICE_URL) as client:
            health = client.health_check()
            logger.info(f"✓ AI Service is healthy")
            logger.info(f"  Status: {health['status']}")
            logger.info(f"  Summarization Model: {health['summarization_model']}")
            logger.info(f"  Embedding Model: {health['embedding_model']}")
            logger.info(f"  Device: {health['device']}")
            return True
    except Exception as e:
        logger.error(f"✗ AI Service health check failed: {e}")
        return False


def test_fetch_articles():
    """Test 2: Fetch articles from database"""
    logger.info("\n" + "=" * 60)
    logger.info("TEST 2: Fetch Articles from Database")
    logger.info("=" * 60)

    try:
        # Get articles without summaries
        articles = ArticleRepository.get_without_summary(limit=3)

        if not articles:
            logger.warning("No articles found without summaries")
            logger.info("Fetching any 3 articles instead...")

            # Fetch any 3 articles
            with get_db_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT article_id, title, content
                        FROM article
                        WHERE content IS NOT NULL AND LENGTH(content) > 100
                        ORDER BY published_at DESC
                        LIMIT 3
                    """)
                    articles = cur.fetchall()

        logger.info(f"✓ Fetched {len(articles)} articles")
        for article in articles:
            logger.info(f"  - Article {article['article_id']}: {article['title'][:50]}...")

        return articles

    except Exception as e:
        logger.error(f"✗ Failed to fetch articles: {e}")
        return []


def test_ai_processing(articles):
    """Test 3: Process articles through AI service"""
    logger.info("\n" + "=" * 60)
    logger.info("TEST 3: AI Processing (Summary + Embedding)")
    logger.info("=" * 60)

    if not articles:
        logger.warning("No articles to process")
        return []

    try:
        # Prepare article inputs
        article_inputs = [
            ArticleInput(
                article_id=article['article_id'],
                content=article['content']
            )
            for article in articles
        ]

        logger.info(f"Processing {len(article_inputs)} articles...")

        # Process through AI service
        with create_ai_client(AI_SERVICE_URL, timeout=120) as client:
            start_time = time.time()
            results = client.process_batch(article_inputs)
            elapsed = time.time() - start_time

        logger.info(f"✓ AI processing completed in {elapsed:.2f}s")

        # Display results
        for result in results:
            logger.info(f"\nArticle {result.article_id}:")
            if result.error:
                logger.error(f"  ✗ Error: {result.error}")
            else:
                logger.info(f"  ✓ Summary: {result.summary[:100]}...")
                logger.info(f"  ✓ Embedding: {len(result.embedding)} dimensions" if result.embedding else "  ✗ No embedding")
                logger.info(f"  ✓ Stance: {result.stance}" if result.stance else "  - Stance: None (model not ready)")

        return results

    except Exception as e:
        logger.error(f"✗ AI processing failed: {e}")
        import traceback
        traceback.print_exc()
        return []


def test_save_to_database(results):
    """Test 4: Save results to database"""
    logger.info("\n" + "=" * 60)
    logger.info("TEST 4: Save Results to Database")
    logger.info("=" * 60)

    if not results:
        logger.warning("No results to save")
        return False

    try:
        for result in results:
            if result.error:
                logger.warning(f"Skipping article {result.article_id} (has error)")
                continue

            # Prepare update data
            update_data = {}

            if result.summary:
                update_data['summary'] = result.summary

            if result.embedding:
                # Convert to pgvector format
                embedding_str = '[' + ','.join(map(str, result.embedding)) + ']'
                update_data['embedding'] = embedding_str

            # Update database
            if update_data:
                ArticleRepository.update_summary_and_embedding(
                    article_id=result.article_id,
                    **update_data
                )
                logger.info(f"✓ Saved article {result.article_id}")

        logger.info(f"✓ All results saved to database")
        return True

    except Exception as e:
        logger.error(f"✗ Failed to save to database: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_verify_database():
    """Test 5: Verify data in database"""
    logger.info("\n" + "=" * 60)
    logger.info("TEST 5: Verify Database Updates")
    logger.info("=" * 60)

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                # Check articles with summaries and embeddings
                cur.execute("""
                    SELECT
                        COUNT(*) as total,
                        COUNT(summary) as with_summary,
                        COUNT(embedding) as with_embedding
                    FROM article
                """)
                stats = cur.fetchone()

                logger.info(f"Database Statistics:")
                logger.info(f"  Total articles: {stats['total']}")
                logger.info(f"  With summaries: {stats['with_summary']}")
                logger.info(f"  With embeddings: {stats['with_embedding']}")

                # Get sample
                cur.execute("""
                    SELECT article_id, title,
                           LEFT(summary, 100) as summary_preview,
                           array_length(embedding, 1) as embedding_dim
                    FROM article
                    WHERE summary IS NOT NULL AND embedding IS NOT NULL
                    ORDER BY updated_at DESC
                    LIMIT 3
                """)
                samples = cur.fetchall()

                logger.info(f"\nSample processed articles:")
                for sample in samples:
                    logger.info(f"  Article {sample['article_id']}: {sample['title'][:40]}...")
                    logger.info(f"    Summary: {sample['summary_preview']}...")
                    logger.info(f"    Embedding: {sample['embedding_dim']} dimensions")

                return True

    except Exception as e:
        logger.error(f"✗ Database verification failed: {e}")
        return False


def main():
    """Run all tests"""
    logger.info("\n" + "=" * 80)
    logger.info("AI PROCESSING PIPELINE TEST")
    logger.info("=" * 80)

    results = []

    # Test 1: Health check
    results.append(("AI Service Health", test_ai_service_health()))

    # Test 2: Fetch articles
    articles = test_fetch_articles()
    results.append(("Fetch Articles", len(articles) > 0))

    if articles:
        # Test 3: AI processing
        ai_results = test_ai_processing(articles)
        results.append(("AI Processing", len(ai_results) > 0))

        if ai_results:
            # Test 4: Save to database
            results.append(("Save to Database", test_save_to_database(ai_results)))

            # Test 5: Verify
            results.append(("Verify Database", test_verify_database()))

    # Summary
    logger.info("\n" + "=" * 80)
    logger.info("TEST SUMMARY")
    logger.info("=" * 80)

    for test_name, passed in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        logger.info(f"{status}: {test_name}")

    all_passed = all(result[1] for result in results)
    logger.info("\n" + ("All tests passed! ✅" if all_passed else "Some tests failed! ❌"))
    logger.info("=" * 80)

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
