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
    title: str
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
        warmup_timeout: int = 120
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
                    "title": article.title,
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

    def cluster_topics_improved(
        self,
        embeddings: List[List[float]],
        texts: List[str],
        article_ids: List[int],
        news_date: str,
        min_topic_size: int = 5,
        nr_topics: str = "auto",
        include_visualization: bool = False,
        viz_dpi: int = 150,
        viz_width: int = 1400,
        viz_height: int = 1400
    ) -> Dict[str, Any]:
        """
        Call HF Spaces IMPROVED BERTopic clustering API with noun-only tokenization.

        Improvements:
        - Noun-only extraction (NNG, NNP, NNB, NR)
        - ngram_range=(1, 2) for better phrases
        - max_df=0.90 for less aggressive filtering
        - Topic titles: 3-6 words

        Args:
            embeddings: List of 768-dim embeddings
            texts: List of "title. summary" strings
            article_ids: List of article IDs
            news_date: YYYY-MM-DD format
            min_topic_size: Minimum articles per topic
            nr_topics: "auto" or integer
            include_visualization: If True, generate visualization (default: False)
            viz_dpi: Visualization DPI (default: 150)
            viz_width: Visualization width in pixels (default: 1400)
            viz_height: Visualization height in pixels (default: 1400)

        Returns:
            {
                'success': bool,
                'topics': List[topic_dict],
                'total_topics': int,
                'total_articles': int,
                'outliers': int,
                'news_date': str,
                'visualization': Optional[str]  # base64-encoded PNG if include_visualization=True
            }
        """
        # Ensure service is warmed up
        if not self._warmed_up:
            if not self.warmup():
                raise ConnectionError("AI service is not available")

        viz_msg = " with visualization" if include_visualization else ""
        logger.info(f"Calling HF Spaces IMPROVED BERTopic clustering API{viz_msg} for {news_date} ({len(article_ids)} articles)")

        payload = {
            "embeddings": embeddings,
            "texts": texts,
            "article_ids": article_ids,
            "news_date": news_date,
            "min_topic_size": min_topic_size,
            "nr_topics": nr_topics,
            "include_visualization": include_visualization,
            "viz_dpi": viz_dpi,
            "viz_width": viz_width,
            "viz_height": viz_height
        }

        last_exception = None
        for attempt in range(1, self.max_retries + 1):
            try:
                logger.debug(f"IMPROVED BERTopic clustering attempt {attempt}/{self.max_retries}")

                response = self.session.post(
                    f"{self.base_url}/cluster-topics-improved",
                    json=payload,
                    timeout=self.timeout,
                    headers={"Content-Type": "application/json"}
                )
                response.raise_for_status()

                result = response.json()

                logger.info(
                    f"IMPROVED BERTopic clustering complete: {result.get('total_topics', 0)} topics "
                    f"from {result.get('total_articles', 0)} articles"
                )

                return result

            except requests.Timeout as e:
                last_exception = e
                logger.warning(f"IMPROVED BERTopic clustering attempt {attempt} timed out: {e}")

            except requests.RequestException as e:
                last_exception = e
                logger.warning(f"IMPROVED BERTopic clustering attempt {attempt} failed: {e}")

            if attempt < self.max_retries:
                backoff_time = 2 ** attempt
                logger.info(f"Retrying in {backoff_time} seconds...")
                time.sleep(backoff_time)

        logger.error(f"IMPROVED BERTopic clustering failed after {self.max_retries} attempts")
        raise last_exception

    def generate_topic_visualization(
        self,
        embeddings: List[List[float]],
        texts: List[str],
        news_date: str,
        dpi: int = 150,
        width: int = 1400,
        height: int = 1400
    ) -> bytes:
        """
        Call HF Spaces visualization generation API.

        Args:
            embeddings: List of 768-dim embeddings
            texts: List of "title. summary" strings
            news_date: YYYY-MM-DD format
            dpi: Image resolution (50-300)
            width: Figure width in pixels
            height: Figure height in pixels

        Returns:
            PNG image bytes
        """
        # Ensure service is warmed up
        if not self._warmed_up:
            if not self.warmup():
                raise ConnectionError("AI service is not available")

        logger.info(f"Calling HF Spaces visualization API for {news_date} ({len(texts)} articles)")

        payload = {
            "embeddings": embeddings,
            "texts": texts,
            "news_date": news_date,
            "dpi": dpi,
            "width": width,
            "height": height
        }

        last_exception = None
        for attempt in range(1, self.max_retries + 1):
            try:
                logger.debug(f"Visualization generation attempt {attempt}/{self.max_retries}")

                response = self.session.post(
                    f"{self.base_url}/generate-topic-visualization",
                    json=payload,
                    timeout=self.timeout,
                    headers={"Content-Type": "application/json"}
                )
                response.raise_for_status()

                logger.info("Visualization generated successfully")
                return response.content

            except requests.Timeout as e:
                last_exception = e
                logger.warning(f"Visualization attempt {attempt} timed out: {e}")

            except requests.RequestException as e:
                last_exception = e
                logger.warning(f"Visualization attempt {attempt} failed: {e}")

            if attempt < self.max_retries:
                backoff_time = 2 ** attempt
                logger.info(f"Retrying in {backoff_time} seconds...")
                time.sleep(backoff_time)

        logger.error(f"Visualization generation failed after {self.max_retries} attempts")
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
