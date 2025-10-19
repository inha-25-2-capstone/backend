"""
Naver News Scraper for Political News

Scrapes Korean political news from Naver News and saves to database.
"""
import time
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, List
import logging

# Selenium libraries
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import WebDriverException, TimeoutException
from webdriver_manager.chrome import ChromeDriverManager

# Database models
from src.models.database import PressRepository, ArticleRepository
from src.utils.logger import setup_logger

# Setup logger
logger = setup_logger("scraper", level="INFO")

# KST timezone
KST = timezone(timedelta(hours=9))


# Press companies to scrape (Naver press codes)
PRESS_COMPANIES = {
    "연합뉴스": "001",
    "조선일보": "023",
    "동아일보": "020",
    "YTN": "052",
    "한겨레": "028",
    "경향신문": "032"
}


class NaverNewsScraper:
    """Scraper for Naver News political articles."""

    def __init__(self, headless: bool = True, delay: int = 2):
        """
        Initialize the scraper.

        Args:
            headless: Run Chrome in headless mode
            delay: Delay between requests (seconds)
        """
        self.headless = headless
        self.delay = delay
        self.driver = None
        self.stats = {
            "total_scraped": 0,
            "total_saved": 0,
            "total_duplicates": 0,
            "total_errors": 0
        }

    def _setup_driver(self):
        """Setup Chrome WebDriver with options."""
        logger.info("Setting up Chrome driver...")
        options = Options()

        if self.headless:
            options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument(
            "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        )

        try:
            self.driver = webdriver.Chrome(
                service=Service(ChromeDriverManager().install()),
                options=options
            )
            logger.info("Chrome driver setup complete (headless mode: %s)", self.headless)
        except WebDriverException as e:
            logger.error(f"Failed to setup Chrome driver: {e}")
            raise

    def _close_driver(self):
        """Close the WebDriver."""
        if self.driver:
            self.driver.quit()
            logger.info("Chrome driver closed")

    def _get_today_date_str(self) -> str:
        """Get today's date in KST (YYYY-MM-DD format)."""
        now_kst = datetime.now(KST)
        return now_kst.strftime("%Y-%m-%d")

    def _scroll_to_load_all(self, press_name: str):
        """
        Scroll page to load all articles via infinite scroll.

        Args:
            press_name: Name of the press for logging
        """
        logger.info(f"Scrolling page to load all articles for {press_name}...")
        last_height = self.driver.execute_script("return document.body.scrollHeight")

        scroll_count = 0
        max_scrolls = 50  # Prevent infinite loops

        while scroll_count < max_scrolls:
            # Scroll to bottom
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")

            # Wait for new content to load
            time.sleep(self.delay)

            # Calculate new scroll height
            new_height = self.driver.execute_script("return document.body.scrollHeight")

            if new_height == last_height:
                logger.info(f"All articles loaded for {press_name} (scrolled {scroll_count} times)")
                break

            last_height = new_height
            scroll_count += 1

        if scroll_count >= max_scrolls:
            logger.warning(f"Reached maximum scroll limit ({max_scrolls}) for {press_name}")

    def _parse_article_detail(self, url: str) -> Optional[Dict[str, any]]:
        """
        Fetch and parse article detail page.

        Args:
            url: Article URL

        Returns:
            Dictionary with article data or None if failed
        """
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                              "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            }
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, "html.parser")

            # Extract title
            title_tag = (
                soup.select_one("h2.media_end_head_headline")
                or soup.select_one("h2#title_area")
            )
            if not title_tag:
                logger.warning(f"Title not found: {url}")
                return None

            # Extract content
            body_tag = (
                soup.select_one("div#newsct_article")
                or soup.select_one("article#dic_area")
            )
            if not body_tag:
                logger.warning(f"Content not found: {url}")
                return None

            # Extract press name
            press_tag = soup.select_one("a.media_end_head_top_logo img")
            if not press_tag or not press_tag.has_attr("alt"):
                logger.warning(f"Press info not found: {url}")
                return None

            # Extract publication date
            date_tag = soup.select_one("span._ARTICLE_DATE_TIME")
            if not date_tag or not date_tag.has_attr("data-date-time"):
                logger.warning(f"Date not found: {url}")
                return None

            # Extract thumbnail (optional)
            img_tag = (
                soup.select_one("span.end_photo_org img")
                or soup.select_one("div#newsct_article img")
            )
            thumbnail_url = None
            if img_tag:
                thumbnail_url = img_tag.get("src") or img_tag.get("data-src")

            # Parse date
            date_str = date_tag["data-date-time"]  # Format: "YYYY-MM-DD HH:MM:SS"
            published_at = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
            published_at = published_at.replace(tzinfo=KST)

            return {
                "title": title_tag.get_text(strip=True),
                "content": body_tag.get_text(strip=True),
                "press_name": press_tag["alt"],
                "url": url,
                "published_at": published_at,
                "thumbnail_url": thumbnail_url
            }

        except requests.RequestException as e:
            logger.error(f"Request failed for {url}: {e}")
            return None
        except Exception as e:
            logger.error(f"Failed to parse article {url}: {e}")
            return None

    def _save_article_to_db(self, article_data: Dict[str, any], press_code: str) -> bool:
        """
        Save article to database.

        Args:
            article_data: Article data dictionary
            press_code: Naver press code (e.g., "001")

        Returns:
            True if saved successfully, False if duplicate or error
        """
        try:
            # Check for duplicates
            if ArticleRepository.exists_by_url(article_data["url"]):
                logger.debug(f"Duplicate article skipped: {article_data['url']}")
                self.stats["total_duplicates"] += 1
                return False

            # Get or create press
            press_id = PressRepository.get_or_create(press_code, article_data["press_name"])

            # Save article
            article_id = ArticleRepository.create(
                press_id=press_id,
                title=article_data["title"],
                content=article_data["content"],
                article_url=article_data["url"],
                published_at=article_data["published_at"],
                img_url=article_data.get("thumbnail_url")
            )

            logger.info(f"Saved article {article_id}: {article_data['title'][:50]}...")
            self.stats["total_saved"] += 1
            return True

        except Exception as e:
            logger.error(f"Failed to save article to DB: {e}")
            self.stats["total_errors"] += 1
            return False

    def scrape_press(self, press_name: str, press_id: str, target_date: str) -> int:
        """
        Scrape articles from a specific press for a target date.

        Args:
            press_name: Name of the press
            press_id: Naver press ID code
            target_date: Target date in YYYY-MM-DD format

        Returns:
            Number of articles saved
        """
        saved_count = 0
        base_url = f"https://media.naver.com/press/{press_id}?sid=100"

        logger.info(f"{'=' * 60}")
        logger.info(f"Starting scraping: {press_name} ({press_id})")
        logger.info(f"Target date: {target_date}")
        logger.info(f"{'=' * 60}")

        try:
            # Navigate to press page
            self.driver.get(base_url)
            logger.info(f"Loaded page: {base_url}")
            time.sleep(3)  # Initial page load

            # Scroll to load all articles
            self._scroll_to_load_all(press_name)

            # Parse loaded page
            soup = BeautifulSoup(self.driver.page_source, "html.parser")
            articles_list = soup.select("ul.press_edit_news_list li.press_edit_news_item")

            logger.info(f"Found {len(articles_list)} article items on page")

            # Process each article
            for idx, article in enumerate(articles_list, 1):
                link_tag = article.select_one("a.press_edit_news_link")
                if not link_tag or not link_tag.has_attr("href"):
                    continue

                url = link_tag["href"]

                # Parse article detail
                article_data = self._parse_article_detail(url)
                if not article_data:
                    continue

                # Check if article is from target date
                article_date = article_data["published_at"].strftime("%Y-%m-%d")
                if article_date != target_date:
                    logger.debug(f"Skipping article from different date: {article_date}")
                    continue

                self.stats["total_scraped"] += 1

                # Save to database
                if self._save_article_to_db(article_data, press_id):
                    saved_count += 1

                # Rate limiting
                time.sleep(self.delay)

            logger.info(f"Completed {press_name}: {saved_count} articles saved")

        except Exception as e:
            logger.error(f"Error scraping {press_name}: {e}")
            self.stats["total_errors"] += 1

        return saved_count

    def run(self, press_companies: Dict[str, str] = None):
        """
        Run the scraper for all press companies.

        Args:
            press_companies: Dictionary of press name -> press ID
                           If None, uses default PRESS_COMPANIES
        """
        if press_companies is None:
            press_companies = PRESS_COMPANIES

        target_date = self._get_today_date_str()
        logger.info(f"Starting scraper for date: {target_date}")
        logger.info(f"Press companies to scrape: {len(press_companies)}")

        try:
            self._setup_driver()

            for press_name, press_id in press_companies.items():
                self.scrape_press(press_name, press_id, target_date)

        except Exception as e:
            logger.error(f"Scraper error: {e}")
            raise

        finally:
            self._close_driver()

        # Print final statistics
        logger.info(f"\n{'=' * 60}")
        logger.info(f"SCRAPING COMPLETE - {target_date}")
        logger.info(f"{'=' * 60}")
        logger.info(f"Total scraped: {self.stats['total_scraped']}")
        logger.info(f"Total saved: {self.stats['total_saved']}")
        logger.info(f"Duplicates skipped: {self.stats['total_duplicates']}")
        logger.info(f"Errors: {self.stats['total_errors']}")
        logger.info(f"{'=' * 60}")


def main():
    """Main entry point for the scraper."""
    scraper = NaverNewsScraper(headless=True, delay=2)
    scraper.run()


if __name__ == "__main__":
    main()