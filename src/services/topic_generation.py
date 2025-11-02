"""
Topic generation service using KeyBERT via HF Spaces API.

This module calls the AI service to generate meaningful topic titles
from clustered articles using KeyBERT.
"""

import logging
from typing import List, Dict, Optional
import requests
from src.config import AI_SERVICE_URL, AI_SERVICE_TIMEOUT

logger = logging.getLogger(__name__)


def generate_topics_from_clusters(
    clusters: List[Dict],
    top_n_keywords: int = 3,
    method: str = "tfidf",
    use_phrases: bool = True,
    keyphrase_ngram_range: tuple = (2, 4)
) -> List[Dict]:
    """
    Generate topic titles from clusters using TF-IDF or KeyBERT via AI service.

    Args:
        clusters: List of cluster data with representative articles
            [
                {
                    "cluster_id": 1,
                    "representative_articles": [
                        {"title": "...", "summary": "..."},
                        ...
                    ]
                }
            ]
        top_n_keywords: Number of keywords to extract per cluster
        method: Extraction method - "tfidf" (default, recommended for Korean) or "keybert"
        use_phrases: Whether to extract multi-word phrases (TF-IDF only)
        keyphrase_ngram_range: N-gram range for keyphrases (KeyBERT only, e.g., (2, 4))

    Returns:
        List of topics with generated titles
            [
                {
                    "cluster_id": 1,
                    "topic_title": "부동산 규제 완화",
                    "keywords": [
                        {"keyword": "부동산 규제 완화", "score": 0.85},
                        ...
                    ]
                }
            ]

    Raises:
        requests.exceptions.RequestException: If API call fails
    """
    if not clusters:
        logger.warning("No clusters provided for topic generation")
        return []

    # Prepare request payload
    payload = {
        "clusters": clusters,
        "top_n_keywords": top_n_keywords,
        "method": method,
        "use_phrases": use_phrases,
        "keyphrase_ngram_range": list(keyphrase_ngram_range)
    }

    logger.info(
        f"Generating topics for {len(clusters)} clusters using {method.upper()} "
        f"(top_n={top_n_keywords})"
    )

    try:
        # Call HF Spaces API
        response = requests.post(
            f"{AI_SERVICE_URL}/generate-topics",
            json=payload,
            timeout=AI_SERVICE_TIMEOUT
        )
        response.raise_for_status()

        result = response.json()
        topics = result.get("topics", [])

        logger.info(
            f"Generated {len(topics)} topics in "
            f"{result.get('processing_time_seconds', 0):.2f}s"
        )

        return topics

    except requests.exceptions.Timeout:
        logger.error("Topic generation timed out")
        raise

    except requests.exceptions.RequestException as e:
        logger.error(f"Topic generation failed: {e}")
        raise


def batch_generate_topics(
    cluster_articles_map: Dict[int, List[Dict]],
    top_n_keywords: int = 3,
    method: str = "tfidf",
    representative_count: int = 5,
    use_phrases: bool = True
) -> Dict[int, Dict]:
    """
    Generate topics for multiple clusters at once.

    Args:
        cluster_articles_map: Mapping of cluster_id to article list
            {
                1: [{"title": "...", "summary": "..."}, ...],
                2: [...],
                ...
            }
        top_n_keywords: Number of keywords per cluster
        method: Extraction method - "tfidf" (default) or "keybert"
        representative_count: Number of representative articles to use per cluster
        use_phrases: Whether to extract multi-word phrases (TF-IDF only)

    Returns:
        Mapping of cluster_id to topic data
            {
                1: {
                    "topic_title": "부동산 규제 완화",
                    "keywords": [...]
                },
                ...
            }
    """
    if not cluster_articles_map:
        logger.warning("No clusters provided for batch topic generation")
        return {}

    # Prepare clusters with representative articles
    clusters = []
    for cluster_id, articles in cluster_articles_map.items():
        # Take top N representative articles
        representative_articles = articles[:representative_count]

        clusters.append({
            "cluster_id": cluster_id,
            "representative_articles": representative_articles
        })

    try:
        topics = generate_topics_from_clusters(
            clusters,
            top_n_keywords=top_n_keywords,
            method=method,
            use_phrases=use_phrases
        )

        # Convert to dict for easy lookup
        topic_dict = {
            topic["cluster_id"]: {
                "topic_title": topic["topic_title"],
                "keywords": topic.get("keywords", [])
            }
            for topic in topics
        }

        logger.info(f"Successfully generated {len(topic_dict)} topics")
        return topic_dict

    except Exception as e:
        logger.error(f"Batch topic generation failed: {e}")
        return {}
