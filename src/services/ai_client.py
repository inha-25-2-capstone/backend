"""
AI Service HTTP Client
Communicates with AI service (HF Spaces) for batch processing
"""
import requests
import time
from typing import List, Dict, Optional, Any
from dataclasses import dataclass
from src.utils.logger import setup_logger

logger = setup_logger()


@dataclass
class ArticleInput:
    """Input article for AI processing"""
    article_id: int
    content: str


@dataclass
class ProcessResult:
    """Result from AI processing"""
    article_id: int
    summary: Optional[str]
    embedding: Optional[List[float]]
    stance: Optional[Dict[str, Any]]
    error: Optional[str]


class AIServiceClient:
    """
    HTTP client for AI service
    Handles batch processing
    """

    def __init__(
        self,
        base_url: str,
        timeout: int = 120,
        max_retries: int = 3,
        warmup_timeout: int = 60
    ):
        """
        Initialize AI service client

        Args:
            base_url: AI service URL
            timeout: Request timeout in seconds
            max_retries: Maximum number of retry attempts
            warmup_timeout: Timeout for initial warmup request (HF Spaces cold start)
        """
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        self.max_retries = max_retries
        self.warmup_timeout = warmup_timeout
        self.session = requests.Session()
        self._warmed_up = False

        logger.info(f"AI Service Client initialized: {self.base_url}")

    def warmup(self) -> bool:
        """
        Warm up HF Spaces if in sleep mode
        Returns True if successful, False otherwise
        """
        if self._warmed_up:
            return True

        logger.info("Warming up AI service (may take up to 60s for HF Spaces cold start)...")
        url = f"{self.base_url}/health"

        for attempt in range(1, 4):  # Try up to 3 times
            try:
                response = self.session.get(url, timeout=self.warmup_timeout)
                response.raise_for_status()
                logger.info("AI service is ready!")
                self._warmed_up = True
                return True
            except requests.Timeout:
                logger.warning(f"Warmup attempt {attempt}/3 timed out, retrying...")
            except requests.RequestException as e:
                logger.warning(f"Warmup attempt {attempt}/3 failed: {e}")

            if attempt < 3:
                time.sleep(5)

        logger.error("Failed to warm up AI service after 3 attempts")
        return False

    def health_check(self) -> Dict[str, Any]:
        """Check AI service health (with warmup if needed)"""
        if not self._warmed_up:
            if not self.warmup():
                raise ConnectionError("AI service is not available")

        url = f"{self.base_url}/health"
        response = self.session.get(url, timeout=30)
        response.raise_for_status()
        return response.json()

    def process_batch(
        self,
        articles: List[ArticleInput],
        max_summary_length: int = 300,
        min_summary_length: int = 150
    ) -> List[ProcessResult]:
        """Process batch of articles"""
        if len(articles) > 50:
            raise ValueError(f"Batch size ({len(articles)}) exceeds maximum (50)")

        if not articles:
            logger.warning("Empty batch provided")
            return []

        # Ensure service is warmed up before processing
        if not self._warmed_up:
            if not self.warmup():
                raise ConnectionError("AI service is not available")

        logger.info(f"Processing batch of {len(articles)} articles")

        payload = {
            "articles": [
                {
                    "article_id": article.article_id,
                    "content": article.content
                }
                for article in articles
            ],
            "max_summary_length": max_summary_length,
            "min_summary_length": min_summary_length
        }

        last_exception = None
        for attempt in range(1, self.max_retries + 1):
            try:
                logger.debug(f"Attempt {attempt}/{self.max_retries}")

                response = self.session.post(
                    f"{self.base_url}/batch-process-articles",
                    json=payload,
                    timeout=self.timeout,
                    headers={"Content-Type": "application/json"}
                )
                response.raise_for_status()

                data = response.json()

                results = [
                    ProcessResult(
                        article_id=result["article_id"],
                        summary=result.get("summary"),
                        embedding=result.get("embedding"),
                        stance=result.get("stance"),
                        error=result.get("error")
                    )
                    for result in data["results"]
                ]

                logger.info(
                    f"Batch processed successfully: "
                    f"{data['successful']}/{data['total_processed']} successful"
                )

                return results

            except requests.Timeout as e:
                last_exception = e
                logger.warning(f"Attempt {attempt} timed out: {e}")

            except requests.RequestException as e:
                last_exception = e
                logger.warning(f"Attempt {attempt} failed: {e}")

            if attempt < self.max_retries:
                backoff_time = 2 ** attempt
                logger.info(f"Retrying in {backoff_time} seconds...")
                time.sleep(backoff_time)

        logger.error(f"Batch processing failed after {self.max_retries} attempts")
        raise last_exception

    def close(self):
        """Close HTTP session"""
        self.session.close()
        logger.debug("AI Service Client session closed")

    def __enter__(self):
        """Context manager entry"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.close()


def create_ai_client(base_url: str, timeout: int = 120) -> AIServiceClient:
    """Factory function to create AI service client"""
    return AIServiceClient(base_url=base_url, timeout=timeout)
