"""
Test script to compare original vs improved BERTopic clustering

Compares:
- Original: CustomTokenizer, ngram=(1,3), max_df=0.6
- Improved: Noun-only tokenizer, ngram=(1,2), max_df=0.90

Usage:
    python scripts/test_improved_clustering.py
"""
import sys
import os
from pathlib import Path
from datetime import date
import asyncio

# Add backend to Python path
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

from src.models.database import SessionLocal
from src.models.article import Article, Topic
from src.services.ai_client import AIServiceClient
from src.utils.config import settings
from src.utils.logger import setup_logger

logger = setup_logger()


async def fetch_embeddings_for_date(news_date: date):
    """Fetch articles with embeddings for given date."""
    db = SessionLocal()
    try:
        articles = (
            db.query(Article)
            .filter(
                Article.news_date == news_date,
                Article.embedding.isnot(None)
            )
            .all()
        )

        if not articles:
            logger.error(f"No articles with embeddings found for {news_date}")
            return None

        embeddings = []
        texts = []
        article_ids = []

        for article in articles:
            embeddings.append(article.embedding)
            # Combine title + summary for BERTopic
            text = f"{article.title}. {article.summary or ''}"
            texts.append(text)
            article_ids.append(article.article_id)

        logger.info(f"Fetched {len(article_ids)} articles with embeddings for {news_date}")

        return {
            'embeddings': embeddings,
            'texts': texts,
            'article_ids': article_ids,
            'news_date': str(news_date)
        }

    finally:
        db.close()


async def test_clustering_comparison(news_date: date):
    """
    Compare original vs improved clustering on the same data.
    """
    logger.info("=" * 80)
    logger.info("BERTopic Clustering Comparison Test")
    logger.info(f"Date: {news_date}")
    logger.info("=" * 80)

    # Fetch data
    data = await fetch_embeddings_for_date(news_date)
    if not data:
        logger.error("Failed to fetch data")
        return

    logger.info(f"\nData: {len(data['article_ids'])} articles\n")

    # Initialize AI client
    ai_client = AIServiceClient(
        base_url=settings.AI_SERVICE_URL,
        timeout=settings.AI_SERVICE_TIMEOUT
    )

    # Test 1: Original clustering (Mecab version)
    logger.info("=" * 80)
    logger.info("TEST 1: ORIGINAL CLUSTERING (Mecab)")
    logger.info("Settings: ngram=(1,3), max_features=3000")
    logger.info("=" * 80)

    try:
        original_result = await ai_client.cluster_topics_mecab(
            embeddings=data['embeddings'],
            texts=data['texts'],
            article_ids=data['article_ids'],
            news_date=data['news_date']
        )

        if original_result['success']:
            logger.info(f"\n✓ Original clustering successful")
            logger.info(f"  Total topics: {original_result['total_topics']}")
            logger.info(f"  Outliers: {original_result['outliers']}")
            logger.info("\n  Top 10 Topics (Original):")

            for topic in original_result['topics'][:10]:
                if topic['topic_rank']:
                    logger.info(
                        f"    Rank {topic['topic_rank']}: '{topic['topic_title']}' "
                        f"({topic['article_count']} articles, "
                        f"length={len(topic['topic_title'])})"
                    )
        else:
            logger.error(f"Original clustering failed: {original_result.get('error')}")

    except Exception as e:
        logger.error(f"Original clustering error: {e}", exc_info=True)
        original_result = None

    # Test 2: Improved clustering
    logger.info("\n" + "=" * 80)
    logger.info("TEST 2: IMPROVED CLUSTERING (Noun-only)")
    logger.info("Settings: noun-only, ngram=(1,2), min_df=2, max_df=0.90")
    logger.info("Title length: 3-6 words")
    logger.info("=" * 80)

    try:
        improved_result = await ai_client.cluster_topics_improved(
            embeddings=data['embeddings'],
            texts=data['texts'],
            article_ids=data['article_ids'],
            news_date=data['news_date']
        )

        if improved_result['success']:
            logger.info(f"\n✓ Improved clustering successful")
            logger.info(f"  Total topics: {improved_result['total_topics']}")
            logger.info(f"  Outliers: {improved_result['outliers']}")
            logger.info("\n  Top 10 Topics (Improved):")

            for topic in improved_result['topics'][:10]:
                if topic['topic_rank']:
                    logger.info(
                        f"    Rank {topic['topic_rank']}: '{topic['topic_title']}' "
                        f"({topic['article_count']} articles, "
                        f"length={len(topic['topic_title'])})"
                    )
        else:
            logger.error(f"Improved clustering failed: {improved_result.get('error')}")

    except Exception as e:
        logger.error(f"Improved clustering error: {e}", exc_info=True)
        improved_result = None

    # Comparison
    logger.info("\n" + "=" * 80)
    logger.info("COMPARISON SUMMARY")
    logger.info("=" * 80)

    if original_result and original_result['success']:
        logger.info(f"\nOriginal:")
        logger.info(f"  Topics: {original_result['total_topics']}")
        logger.info(f"  Outliers: {original_result['outliers']}")

        # Show all original titles
        logger.info("\n  All Original Topic Titles:")
        for i, topic in enumerate(original_result['topics'][:10], 1):
            if topic['topic_rank']:
                logger.info(f"    {i}. '{topic['topic_title']}' (len={len(topic['topic_title'])})")

    if improved_result and improved_result['success']:
        logger.info(f"\nImproved:")
        logger.info(f"  Topics: {improved_result['total_topics']}")
        logger.info(f"  Outliers: {improved_result['outliers']}")

        # Show all improved titles
        logger.info("\n  All Improved Topic Titles:")
        for i, topic in enumerate(improved_result['topics'][:10], 1):
            if topic['topic_rank']:
                word_count = len(topic['topic_title'].split())
                logger.info(f"    {i}. '{topic['topic_title']}' (words={word_count})")

        # Check title word count compliance
        title_word_counts = [
            len(t['topic_title'].split()) for t in improved_result['topics'][:10]
            if t['topic_rank']
        ]
        logger.info(f"\n  Title Word Count Stats:")
        logger.info(f"    Min: {min(title_word_counts) if title_word_counts else 0}")
        logger.info(f"    Max: {max(title_word_counts) if title_word_counts else 0}")
        logger.info(f"    Avg: {sum(title_word_counts)/len(title_word_counts) if title_word_counts else 0:.1f}")
        logger.info(f"    3-6 words: {sum(1 for l in title_word_counts if 3 <= l <= 6)}/{len(title_word_counts)}")

    logger.info("\n" + "=" * 80)
    logger.info("Test complete!")
    logger.info("=" * 80)


async def main():
    """Main test function."""
    # Test with today's date
    today = date(2025, 11, 27)

    await test_clustering_comparison(today)


if __name__ == "__main__":
    asyncio.run(main())
