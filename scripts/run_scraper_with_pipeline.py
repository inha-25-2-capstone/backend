#!/usr/bin/env python3
"""
Scraper with Celery Pipeline Trigger

This script runs every 30 minutes:
1. Scrapes new articles from Naver News
2. Triggers Celery chain: AI processing -> Incremental assignment

Designed for real-time news pipeline with Render Cron.
"""
import sys
from pathlib import Path
from datetime import datetime

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.scrapers.scraper import NaverNewsScraper, PRESS_COMPANIES
from src.workers.tasks import process_articles_batch, incremental_assign_articles
from src.models.database import get_db_cursor
from src.utils.logger import setup_logger

logger = setup_logger("scraper_pipeline", level="INFO")


def get_unprocessed_articles(limit=100):
    """
    Get articles that need AI processing (no embedding yet).

    Args:
        limit: Maximum number of articles to fetch

    Returns:
        List of article IDs
    """
    with get_db_cursor() as cur:
        cur.execute(
            """
            SELECT article_id
            FROM article
            WHERE embedding IS NULL
            ORDER BY published_at DESC
            LIMIT %s
            """,
            (limit,)
        )
        results = cur.fetchall()

    article_ids = [row['article_id'] for row in results]
    return article_ids


def main():
    """Run scraper and trigger Celery pipeline."""
    logger.info("=" * 80)
    logger.info("SCRAPER + CELERY PIPELINE")
    logger.info("=" * 80)

    # =====================================================================
    # STEP 1: SCRAPING
    # =====================================================================
    logger.info("\n📰 STEP 1: Scraping new articles...")

    try:
        scraper = NaverNewsScraper(headless=True, delay=2)
        scraper.run(press_companies=PRESS_COMPANIES)

        stats = scraper.stats
        logger.info("✅ Scraping completed")
        logger.info(f"  📊 Total scraped: {stats['total_scraped']}")
        logger.info(f"  💾 Saved: {stats['total_saved']}")
        logger.info(f"  🔁 Duplicates: {stats['total_duplicates']}")

    except Exception as e:
        logger.error(f"❌ Scraping failed: {e}", exc_info=True)
        return 1

    # =====================================================================
    # STEP 2: TRIGGER CELERY PIPELINE
    # =====================================================================
    logger.info("\n🔗 STEP 2: Triggering Celery pipeline...")

    # Get articles that need processing
    article_ids = get_unprocessed_articles(limit=100)

    if not article_ids:
        logger.info("ℹ️  No new articles to process")
        logger.info("✅ Script completed (nothing to process)")
        return 0

    logger.info(f"📋 Found {len(article_ids)} articles needing AI processing")

    # Split into batches of 5 for faster processing
    batch_size = 5
    batches = [article_ids[i:i+batch_size] for i in range(0, len(article_ids), batch_size)]

    logger.info(f"📦 Creating {len(batches)} batches (size: {batch_size})")

    # Create Celery chain for each batch
    # Chain: AI processing -> Incremental assignment
    today_str = datetime.now().strftime("%Y-%m-%d")

    for i, batch in enumerate(batches, 1):
        # Create chain: process_articles_batch -> incremental_assign_articles
        from celery import chain

        pipeline = chain(
            process_articles_batch.si(batch),
            incremental_assign_articles.si(news_date_str=today_str, since_minutes=35)
        )

        # Trigger async execution
        pipeline.apply_async()

        logger.info(f"  ✅ Batch {i}/{len(batches)}: {len(batch)} articles -> Celery chain triggered")

    # =====================================================================
    # SUMMARY
    # =====================================================================
    logger.info("\n" + "=" * 80)
    logger.info("✅ SCRAPER COMPLETED - CELERY PIPELINE TRIGGERED")
    logger.info("=" * 80)
    logger.info(f"📰 Articles scraped: {stats['total_saved']}")
    logger.info(f"🤖 Articles queued for AI: {len(article_ids)}")
    logger.info(f"📦 Celery batches created: {len(batches)}")
    logger.info("")
    logger.info("🔄 Next steps (handled by Celery Worker):")
    logger.info("   1. AI processing (summary + embedding)")
    logger.info("   2. Incremental assignment to topics")
    logger.info("   3. Centroid updates")
    logger.info("")
    logger.info("💡 Monitor: Check Celery Worker logs for progress")
    logger.info("=" * 80)

    return 0


if __name__ == "__main__":
    sys.exit(main())
