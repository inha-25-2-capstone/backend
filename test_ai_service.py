#!/usr/bin/env python3
"""
Test script for AI service /batch-process-articles endpoint
Fetches real articles from database and tests summarization
"""
import sys
import requests
import json
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from src.models.database import ArticleRepository, init_connection_pool
from src.utils.logger import setup_logger

logger = setup_logger("test_ai_service", level="INFO")

# AI service URL (change to HF Spaces URL when deployed)
AI_SERVICE_URL = "http://localhost:7860"


def test_batch_process_articles():
    """Test the /batch-process-articles endpoint with real DB data."""
    logger.info("Testing AI service /batch-process-articles endpoint...")

    # Initialize DB connection
    init_connection_pool()

    # Fetch 3 articles without summaries
    articles = ArticleRepository.get_without_summary(limit=3)
    logger.info(f"Fetched {len(articles)} articles from database")

    # Prepare API request
    request_data = {
        "articles": [
            {
                "article_id": article["article_id"],
                "content": article["content"]
            }
            for article in articles
        ],
        "max_summary_length": 128
    }

    logger.info(f"Sending request to {AI_SERVICE_URL}/batch-process-articles")
    logger.info(f"Number of articles: {len(request_data['articles'])}")

    # Send request
    try:
        response = requests.post(
            f"{AI_SERVICE_URL}/batch-process-articles",
            json=request_data,
            timeout=60
        )
        response.raise_for_status()

        result = response.json()

        # Print results
        logger.info("=" * 60)
        logger.info("AI SERVICE RESPONSE")
        logger.info("=" * 60)
        logger.info(f"Total processed: {result['total_processed']}")
        logger.info(f"Successful: {result['successful']}")
        logger.info(f"Failed: {result['failed']}")
        logger.info(f"Processing time: {result.get('processing_time_seconds', 0):.2f}s")
        logger.info("=" * 60)

        # Print individual results
        for idx, res in enumerate(result['results'], 1):
            logger.info(f"\nArticle {idx} (ID: {res['article_id']}):")
            logger.info(f"  Title: {articles[idx-1]['title'][:60]}...")
            logger.info(f"  Original length: {len(articles[idx-1]['content'])} chars")

            if res['error']:
                logger.error(f"  ❌ Error: {res['error']}")
            else:
                logger.info(f"  ✅ Summary: {res['summary']}")
                logger.info(f"  Summary length: {len(res['summary'])} chars")
                logger.info(f"  Stance: {res['stance']}")  # Should be None for now

        logger.info("\n" + "=" * 60)
        logger.info("TEST COMPLETE")
        logger.info("=" * 60)

        return result

    except requests.exceptions.RequestException as e:
        logger.error(f"❌ Request failed: {e}")
        return None
    except Exception as e:
        logger.error(f"❌ Test failed: {e}", exc_info=True)
        return None


def test_health_check():
    """Test the /health endpoint."""
    logger.info("Testing AI service /health endpoint...")

    try:
        response = requests.get(f"{AI_SERVICE_URL}/health", timeout=10)
        response.raise_for_status()

        health = response.json()
        logger.info("=" * 60)
        logger.info("HEALTH CHECK")
        logger.info("=" * 60)
        logger.info(f"Status: {health['status']}")
        logger.info(f"Summarization model: {health['summarization_model']}")
        logger.info(f"Stance model: {health['stance_model']}")
        logger.info(f"Device: {health['device']}")
        logger.info("=" * 60)

        return health

    except requests.exceptions.RequestException as e:
        logger.error(f"❌ Health check failed: {e}")
        return None


if __name__ == "__main__":
    # Test health check first
    health = test_health_check()

    if health and health['status'] == 'healthy':
        print()
        # Test batch processing
        test_batch_process_articles()
    else:
        logger.error("❌ AI service is not healthy. Please start the service first.")
        logger.info("To start the AI service:")
        logger.info("  cd /home/zedwrkc/inha_capstone/AI")
        logger.info("  python -m uvicorn app:app --host 0.0.0.0 --port 7860")
