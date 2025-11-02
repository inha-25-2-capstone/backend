#!/usr/bin/env python3
"""
Process all articles without summaries through AI pipeline
"""
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.models.database import ArticleRepository
from src.workers.tasks import process_articles_batch
from src.utils.logger import setup_logger

logger = setup_logger("process_articles", level="INFO")

BATCH_SIZE = 5  # Process articles in smaller batches


def main():
    """Process all articles without summaries"""
    logger.info("=" * 60)
    logger.info("Processing Articles Through AI Pipeline")
    logger.info("=" * 60)

    # Get articles without summaries
    logger.info("Fetching articles without summaries...")
    articles = ArticleRepository.get_without_summary(limit=None)  # Get all

    if not articles:
        logger.info("No articles to process!")
        return 0

    total_articles = len(articles)
    logger.info(f"Found {total_articles} articles to process")

    # Split into batches
    batches = []
    for i in range(0, total_articles, BATCH_SIZE):
        batch = articles[i:i + BATCH_SIZE]
        batch_ids = [article['article_id'] for article in batch]
        batches.append(batch_ids)

    logger.info(f"Split into {len(batches)} batches of {BATCH_SIZE} articles")
    logger.info("=" * 60)

    # Process each batch synchronously (for simplicity)
    successful_batches = 0
    failed_batches = 0

    for idx, batch_ids in enumerate(batches, 1):
        logger.info(f"\nProcessing batch {idx}/{len(batches)} ({len(batch_ids)} articles)...")

        try:
            # Call task directly (synchronous)
            result = process_articles_batch(batch_ids)

            logger.info(f"Batch {idx} result:")
            logger.info(f"  Status: {result.get('status', 'unknown')}")
            logger.info(f"  Successful: {result.get('successful', 0)}")
            logger.info(f"  Failed: {result.get('failed', 0)}")

            if result.get('status') == 'success':
                successful_batches += 1
            else:
                failed_batches += 1

        except Exception as e:
            logger.error(f"Batch {idx} failed with error: {e}")
            failed_batches += 1

    # Final summary
    logger.info("\n" + "=" * 60)
    logger.info("Processing Complete!")
    logger.info("=" * 60)
    logger.info(f"Total articles: {total_articles}")
    logger.info(f"Total batches: {len(batches)}")
    logger.info(f"Successful batches: {successful_batches}")
    logger.info(f"Failed batches: {failed_batches}")
    logger.info("=" * 60)

    return 0 if failed_batches == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
