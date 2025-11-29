#!/usr/bin/env python3
"""
Run BERTopic clustering for 2025-11-27 articles (improved version)
"""
import sys
from datetime import date

# Add backend to path
sys.path.insert(0, '/home/zedwrkc/inha_capstone/backend')

from src.workers.tasks import bertopic_clustering_task
from src.utils.logger import setup_logger

logger = setup_logger()

if __name__ == "__main__":
    logger.info("=" * 80)
    logger.info("Running Improved BERTopic Clustering for 2025-11-27")
    logger.info("=" * 80)

    news_date = "2025-11-27"

    # Run clustering task directly (synchronous for testing)
    try:
        result = bertopic_clustering_task(news_date_str=news_date, limit=None)

        logger.info("\n" + "=" * 80)
        logger.info("CLUSTERING RESULTS")
        logger.info("=" * 80)

        if result.get('success'):
            logger.info(f"✅ Success!")
            logger.info(f"Total topics: {result.get('total_topics')}")
            logger.info(f"Total articles: {result.get('total_articles')}")
            logger.info(f"Outliers: {result.get('outliers')}")
            logger.info(f"Topics saved: {result.get('topics_saved')}")
            logger.info(f"Mappings saved: {result.get('mappings_saved')}")

            if result.get('visualization_saved'):
                logger.info(f"✅ Visualization saved to database")
        else:
            logger.error(f"❌ Clustering failed: {result.get('error')}")

    except Exception as e:
        logger.error(f"❌ Error: {e}", exc_info=True)
        sys.exit(1)

    logger.info("\n" + "=" * 80)
    logger.info("Clustering Complete!")
    logger.info("=" * 80)
