#!/usr/bin/env python3
"""
Test deployed AI service on HF Spaces with real articles from database
"""
import sys
import requests
from pathlib import Path

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from src.models.database import ArticleRepository, init_connection_pool
from src.utils.logger import setup_logger

logger = setup_logger("test_deployed_ai", level="INFO")

# Deployed AI service URL
AI_SERVICE_URL = "https://zedwrkc-news-stance-detection.hf.space"


def test_health_check():
    """Test health check endpoint"""
    logger.info("Testing health check endpoint...")

    try:
        response = requests.get(f"{AI_SERVICE_URL}/health", timeout=10)
        response.raise_for_status()

        result = response.json()
        logger.info(f"✅ Health check passed: {result}")
        return True
    except Exception as e:
        logger.error(f"❌ Health check failed: {e}")
        return False


def test_summarization():
    """Test summarization with real articles from database"""
    logger.info("Testing summarization with real articles...")

    init_connection_pool()

    # Get 5 articles for testing
    test_article_ids = [1, 5, 10, 15, 20]

    articles = []
    for article_id in test_article_ids:
        article = ArticleRepository.get_by_id(article_id)
        if article:
            articles.append(article)

    if not articles:
        logger.error("❌ No articles found in database")
        return False

    logger.info(f"Fetched {len(articles)} articles for testing")

    # Prepare request
    request_data = {
        "articles": [
            {
                "article_id": article["article_id"],
                "content": article["content"]
            }
            for article in articles
        ]
    }

    logger.info(f"Sending request to {AI_SERVICE_URL}/batch-process-articles")

    try:
        response = requests.post(
            f"{AI_SERVICE_URL}/batch-process-articles",
            json=request_data,
            timeout=120  # Longer timeout for model inference
        )
        response.raise_for_status()

        result = response.json()

        logger.info("=" * 80)
        logger.info("DEPLOYED AI SERVICE TEST RESULTS")
        logger.info("=" * 80)
        logger.info(f"Total processed: {result['total_processed']}")
        logger.info(f"Successful: {result['successful']}")
        logger.info(f"Failed: {result['failed']}")
        logger.info(f"Processing time: {result.get('processing_time_seconds', 0):.2f}s")
        logger.info("=" * 80)

        for idx, res in enumerate(result['results'], 1):
            article = articles[idx-1]
            logger.info(f"\nArticle {idx} (ID: {res['article_id']}):")
            logger.info(f"  Title: {article['title'][:60]}...")
            logger.info(f"  Content length: {len(article['content'])} chars")
            logger.info(f"  Content preview: {article['content'][:100]}...")

            if res['error']:
                logger.error(f"  ❌ Error: {res['error']}")
            else:
                logger.info(f"  ✅ Summary: {res['summary']}")
                logger.info(f"  Summary length: {len(res['summary'])} chars")
                logger.info(f"  Stance: {res['stance']}")

        logger.info("\n" + "=" * 80)
        logger.info("✅ DEPLOYED AI SERVICE TEST COMPLETE")
        logger.info("=" * 80)

        return True

    except Exception as e:
        logger.error(f"❌ Summarization test failed: {e}", exc_info=True)
        return False


if __name__ == "__main__":
    logger.info("Starting deployed AI service tests...")
    logger.info(f"AI Service URL: {AI_SERVICE_URL}")
    logger.info("=" * 80)

    # Test 1: Health check
    health_ok = test_health_check()
    logger.info("")

    # Test 2: Summarization
    if health_ok:
        summarization_ok = test_summarization()
    else:
        logger.error("Skipping summarization test due to health check failure")
        summarization_ok = False

    # Final result
    logger.info("")
    logger.info("=" * 80)
    if health_ok and summarization_ok:
        logger.info("✅ ALL TESTS PASSED - Deployment successful!")
    else:
        logger.error("❌ SOME TESTS FAILED - Check logs above")
    logger.info("=" * 80)
