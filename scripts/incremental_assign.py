#!/usr/bin/env python3
"""
Incremental Topic Assignment Script

Assigns new articles to existing topics based on centroid similarity.
This script runs every 30 minutes to process newly scraped articles.

Usage:
    python scripts/incremental_assign.py [--date YYYY-MM-DD] [--dry-run]

Environment Variables:
    DATABASE_URL or DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD
    INCREMENTAL_SIMILARITY_THRESHOLD (default: 0.5)
    INCREMENTAL_CENTROID_UPDATE_WEIGHT (default: 0.1)
"""

import sys
import os
import logging
import argparse
from datetime import datetime, timedelta
from pathlib import Path

# Add backend to Python path
backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

# Import services
from src.services.incremental_assignment import IncrementalAssigner
from src.models.database import get_db_connection
from src.utils.logger import setup_logger

# Setup logger
logger = setup_logger(name="incremental_assign", level="INFO", log_file="logs/incremental_assign.log")


def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Assign new articles to existing topics incrementally"
    )
    parser.add_argument(
        "--date",
        type=str,
        help="Target date (YYYY-MM-DD). Default: today in KST",
        default=None,
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run without making database changes",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        help="Similarity threshold override (default: from env or 0.5)",
        default=None,
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose logging",
    )
    return parser.parse_args()


def get_target_date(date_str=None):
    """
    Get target date in KST timezone.

    Args:
        date_str: Optional date string (YYYY-MM-DD)

    Returns:
        datetime.date: Target date
    """
    from datetime import timezone, timedelta

    kst = timezone(timedelta(hours=9))
    now_kst = datetime.now(kst)

    if date_str:
        try:
            return datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError as e:
            logger.error(f"Invalid date format: {date_str}. Expected YYYY-MM-DD")
            raise
    else:
        return now_kst.date()


def main():
    """Main execution function."""
    args = parse_arguments()

    # Configure logging level
    if args.verbose:
        logger.setLevel(logging.DEBUG)
        logging.getLogger("services.incremental_assignment").setLevel(logging.DEBUG)

    logger.info("=" * 80)
    logger.info("Starting Incremental Topic Assignment")
    logger.info("=" * 80)

    # Get target date
    target_date = get_target_date(args.date)
    logger.info(f"Target date: {target_date}")

    if args.dry_run:
        logger.info("🔍 DRY RUN MODE - No database changes will be made")

    # Initialize database connection
    try:
        with get_db_connection() as conn:
            logger.info("✓ Database connection established")

            # Initialize incremental assigner
            assigner = IncrementalAssigner(conn)
            logger.info("✓ IncrementalAssigner initialized")

            # Override threshold if specified
            if args.threshold is not None:
                logger.info(f"Overriding similarity threshold: {args.threshold}")
                assigner.similarity_threshold = args.threshold
            else:
                logger.info(f"Using similarity threshold: {assigner.similarity_threshold}")

            # Step 1: Check for active topics
            logger.info("\n📊 Checking for active topics...")
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT COUNT(*)
                    FROM topic
                    WHERE topic_date = %s AND is_active = TRUE
                    """,
                    (target_date,)
                )
                active_topic_count = cur.fetchone()[0]

            if active_topic_count == 0:
                logger.warning(f"⚠️  No active topics found for {target_date}")
                logger.info("💡 Run clustering first: python scripts/run_clustering.py")
                return 1

            logger.info(f"✓ Found {active_topic_count} active topics")

            # Step 2: Check for pending articles
            logger.info("\n📰 Checking for pending articles...")
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT COUNT(*)
                    FROM pending_articles p
                    JOIN article a ON p.article_id = a.article_id
                    WHERE a.news_date = %s
                    """,
                    (target_date,)
                )
                pending_count = cur.fetchone()[0]

            if pending_count == 0:
                logger.info("✓ No pending articles to process")
                return 0

            logger.info(f"✓ Found {pending_count} pending articles")

            # Step 3: Process pending articles
            if args.dry_run:
                logger.info("\n🔍 Simulating assignment (dry run)...")
                # Fetch pending articles
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT p.article_id, p.added_at
                        FROM pending_articles p
                        JOIN article a ON p.article_id = a.article_id
                        WHERE a.news_date = %s
                        ORDER BY p.added_at
                        LIMIT 100
                        """,
                        (target_date,)
                    )
                    pending_articles = cur.fetchall()

                logger.info(f"Would process {len(pending_articles)} articles")
                for article_id, added_at in pending_articles[:5]:  # Show first 5
                    logger.info(f"  - Article {article_id} (added: {added_at})")
                if len(pending_articles) > 5:
                    logger.info(f"  ... and {len(pending_articles) - 5} more")

            else:
                logger.info("\n🔄 Processing pending articles...")
                results = assigner.run_incremental_assignment(target_date)

                # Display results
                logger.info("\n" + "=" * 80)
                logger.info("📊 Assignment Results")
                logger.info("=" * 80)
                logger.info(f"New articles:        {results['new_articles']}")
                logger.info(f"Successfully assigned: {results['assigned']}")
                logger.info(f"Pending (low similarity): {results['pending']}")
                logger.info(f"Topics updated:      {results['updated_topics']}")

                # Check remaining pending articles
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT COUNT(*)
                        FROM pending_articles p
                        JOIN article a ON p.article_id = a.article_id
                        WHERE a.news_date = %s
                        """,
                        (target_date,)
                    )
                    remaining = cur.fetchone()[0]

                logger.info(f"\n📋 Remaining pending articles: {remaining}")

            logger.info("\n✅ Incremental assignment completed successfully")
            return 0

    except Exception as e:
        logger.error(f"❌ Error during incremental assignment: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
