#!/usr/bin/env python3
"""
Full News Pipeline (1-hour cycle)

Complete pipeline that runs every hour:
1. Scraping (Naver News) - synchronous
2. AI Processing (Summary + Embedding) - Celery task
3. BERTopic Clustering - Celery task
4. Stance Analysis - Celery task (TODO)

Uses Celery Chain for async processing.
"""
import sys
from pathlib import Path
from datetime import datetime, timedelta
import pytz

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import os
import redis
from src.scrapers.scraper import NaverNewsScraper, PRESS_COMPANIES
from src.workers.tasks import process_articles_batch
from src.models.database import get_db_cursor
from src.utils.logger import setup_logger

logger = setup_logger("full_pipeline", level="INFO")

# Redis client for batch coordination
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
redis_client = redis.from_url(REDIS_URL, decode_responses=True)

# KST timezone for news_date calculation
KST = pytz.timezone('Asia/Seoul')
NEWS_CUTOFF_HOUR = 5  # 5:00 AM KST cutoff


def get_news_date():
    """
    Calculate news_date based on KST 5:00 AM cutoff.

    Articles published before 5:00 AM belong to previous day.
    This ensures consistency with the scraper's news_date assignment.

    Returns:
        date: The news_date for current pipeline execution
    """
    now_kst = datetime.now(KST)

    if now_kst.hour < NEWS_CUTOFF_HOUR:
        # Before 5:00 AM - use previous day
        news_date = (now_kst - timedelta(days=1)).date()
    else:
        # After 5:00 AM - use current day
        news_date = now_kst.date()

    return news_date


def get_unprocessed_articles(news_date_str: str, limit=None):
    """
    Get articles that need AI processing (no embedding yet) for a specific news_date.

    Args:
        news_date_str: Target news_date (YYYY-MM-DD format)
        limit: Maximum number of articles to fetch (None = no limit)

    Returns:
        List of article IDs
    """
    with get_db_cursor() as cur:
        if limit:
            cur.execute(
                """
                SELECT article_id
                FROM article
                WHERE embedding IS NULL
                  AND news_date = %s
                ORDER BY published_at DESC
                LIMIT %s
                """,
                (news_date_str, limit)
            )
        else:
            cur.execute(
                """
                SELECT article_id
                FROM article
                WHERE embedding IS NULL
                  AND news_date = %s
                ORDER BY published_at DESC
                """,
                (news_date_str,)
            )
        results = cur.fetchall()

    article_ids = [row['article_id'] for row in results]
    return article_ids


def main():
    """Run full pipeline."""
    logger.info("=" * 100)
    logger.info("FULL NEWS PIPELINE (1-HOUR CYCLE)")
    logger.info("=" * 100)

    # =========================================================================
    # STEP 1: SCRAPING
    # =========================================================================
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
        logger.info("⚠️  Continuing with AI processing of existing unprocessed articles...")
        # Set empty stats to continue with pipeline
        stats = {'total_scraped': 0, 'total_saved': 0, 'total_duplicates': 0}

    # =========================================================================
    # STEP 2: TRIGGER CELERY CHAIN
    # =========================================================================
    logger.info("\n🔗 STEP 2: Triggering Celery Chain (AI → BERTopic → Stance)...")

    # Calculate news_date based on KST 5:00 AM cutoff
    news_date = get_news_date()
    news_date_str = news_date.strftime("%Y-%m-%d")
    logger.info(f"📅 Target news_date: {news_date_str} (KST 5:00 AM cutoff)")

    # Get articles that need processing for today's news_date (no limit - process all)
    article_ids = get_unprocessed_articles(news_date_str, limit=None)

    if not article_ids:
        logger.info("ℹ️  No new articles to process")
        logger.info("✅ Pipeline completed (nothing to process)")
        return 0

    logger.info(f"📋 Found {len(article_ids)} articles needing AI processing (news_date: {news_date_str})")

    # Split into batches of 5 for AI processing
    batch_size = 5
    batches = [article_ids[i:i+batch_size] for i in range(0, len(article_ids), batch_size)]

    logger.info(f"📦 Creating {len(batches)} AI processing batches (size: {batch_size})")

    # Redis counter: Set total batches for this news_date
    counter_key = f"ai_batch_completed:{news_date_str}"
    total_key = f"ai_batch_total:{news_date_str}"

    # Clean up any old keys
    redis_client.delete(counter_key)
    redis_client.set(total_key, len(batches))

    logger.info(f"📊 Redis counter initialized: 0/{len(batches)} batches")

    # Trigger AI processing batches (with target_news_date)
    for i, batch in enumerate(batches, 1):
        process_articles_batch.apply_async(args=[batch, news_date_str])
        logger.info(f"  ✅ Batch {i}/{len(batches)}: {len(batch)} articles → AI task queued (news_date: {news_date_str})")

    logger.info(f"  🎯 BERTopic will auto-trigger when all {len(batches)} batches complete (Redis counter)")

    # TODO: Stance analysis task
    logger.info("  ℹ️  Stance analysis: Skipped (model not ready)")

    # =========================================================================
    # SUMMARY
    # =========================================================================
    logger.info("\n" + "=" * 100)
    logger.info("✅ PIPELINE SCRIPT COMPLETED - CELERY TASKS QUEUED")
    logger.info("=" * 100)
    logger.info(f"📰 Articles scraped: {stats['total_saved']}")
    logger.info(f"🤖 Articles queued for AI: {len(article_ids)}")
    logger.info(f"📦 AI batches created: {len(batches)}")
    logger.info("")
    logger.info("🔄 Celery tasks:")
    logger.info(f"   1. AI Processing: {len(batches)} batches running in Celery Worker")
    logger.info(f"   2. BERTopic Clustering: Will auto-trigger via Redis counter (0/{len(batches)} complete)")
    logger.info(f"   3. Stance Analysis: TODO (model not ready)")
    logger.info("")
    logger.info("💡 Monitor: Check Celery Worker logs for progress")
    logger.info("🔄 Next run: 1 hour (KST 5:00 AM cutoff for news_date)")
    logger.info("=" * 100)

    return 0


if __name__ == "__main__":
    sys.exit(main())
