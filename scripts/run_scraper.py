#!/usr/bin/env python3
"""
Script to run the Naver News scraper.

This script can be run manually or scheduled as a cron job.
"""
import sys
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.scrapers.scraper import NaverNewsScraper, PRESS_COMPANIES
from src.utils.logger import setup_logger

logger = setup_logger("run_scraper", level="INFO")


def main():
    """Run the scraper."""
    logger.info("Starting Naver News scraper...")

    try:
        # Initialize scraper with configuration
        scraper = NaverNewsScraper(
            headless=True,  # Run in headless mode for server environments
            delay=2  # 2 second delay between requests
        )

        # Run scraper for all configured press companies
        scraper.run(press_companies=PRESS_COMPANIES)

        logger.info("Scraper completed successfully!")
        return 0

    except KeyboardInterrupt:
        logger.warning("Scraper interrupted by user")
        return 130

    except Exception as e:
        logger.error(f"Scraper failed with error: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
