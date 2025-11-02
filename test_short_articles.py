#!/usr/bin/env python3
"""
Test AI service with short articles (< 150 tokens)
"""
import sys
import requests
from pathlib import Path

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from src.models.database import ArticleRepository, init_connection_pool
from src.utils.logger import setup_logger

logger = setup_logger("test_short_articles", level="INFO")

AI_SERVICE_URL = "http://localhost:7860"


def test_short_articles():
    """Test with articles that have < 150 tokens."""
    logger.info("Testing AI service with SHORT articles...")

    init_connection_pool()

    # Get articles with IDs that we know are short
    # From previous check: Article 12 (126 tokens), 18 (79), 37 (20), 63 (11), 74 (56)
    short_article_ids = [12, 18, 37, 63, 74]

    articles = []
    for article_id in short_article_ids:
        article = ArticleRepository.get_by_id(article_id)
        if article:
            articles.append(article)

    logger.info(f"Fetched {len(articles)} short articles")

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
            timeout=60
        )
        response.raise_for_status()

        result = response.json()

        logger.info("=" * 60)
        logger.info("SHORT ARTICLES TEST RESULTS")
        logger.info("=" * 60)
        logger.info(f"Total processed: {result['total_processed']}")
        logger.info(f"Successful: {result['successful']}")
        logger.info(f"Failed: {result['failed']}")
        logger.info(f"Processing time: {result.get('processing_time_seconds', 0):.2f}s")
        logger.info("=" * 60)

        for idx, res in enumerate(result['results'], 1):
            article = articles[idx-1]
            logger.info(f"\nArticle {idx} (ID: {res['article_id']}):")
            logger.info(f"  Title: {article['title'][:50]}...")
            logger.info(f"  Original length: {len(article['content'])} chars")
            logger.info(f"  Content: {article['content'][:100]}...")

            if res['error']:
                logger.error(f"  ❌ Error: {res['error']}")
            else:
                logger.info(f"  ✅ Summary: {res['summary']}")
                logger.info(f"  Summary length: {len(res['summary'])} chars")

        logger.info("\n" + "=" * 60)
        logger.info("TEST COMPLETE")
        logger.info("=" * 60)

    except Exception as e:
        logger.error(f"❌ Test failed: {e}", exc_info=True)


if __name__ == "__main__":
    test_short_articles()
